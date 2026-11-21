import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import setup
import xdvdfs

spec = importlib.util.spec_from_file_location('builder', ROOT / 'packaging/appimage/builder.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def executable():
    data = bytearray(64)
    data[:4] = b'XEX2'
    struct.pack_into('>I', data, 20, 1)
    struct.pack_into('>II', data, 24, 0x40006, 32)
    struct.pack_into('>I', data, 44, setup.TITLE_ID)
    return bytes(data)


def directory_entry(name, sector, size, attr=0, right=0):
    encoded = name.encode('latin-1')
    return struct.pack('<HHIIBB', 0, right, sector, size, attr, len(encoded)) + encoded


def disc_image(data):
    image = bytearray(80 * xdvdfs.SECTOR)
    marker = 32 * xdvdfs.SECTOR
    image[marker:marker + len(xdvdfs.MAGIC)] = xdvdfs.MAGIC
    struct.pack_into('<II', image, marker + len(xdvdfs.MAGIC), 40, 64)
    first = directory_entry('default.xex', 60, len(data), right=8)
    second = directory_entry('resources', 41, 32, attr=xdvdfs.ATTR_DIRECTORY)
    image[40 * 2048:40 * 2048 + len(first)] = first
    image[40 * 2048 + 32:40 * 2048 + 32 + len(second)] = second
    resource = directory_entry('test.dat', 61, 5)
    image[41 * 2048:41 * 2048 + len(resource)] = resource
    image[60 * 2048:60 * 2048 + len(data)] = data
    image[61 * 2048:61 * 2048 + 5] = b'hello'
    return image


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='fracture test ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = executable()
        self.digest = hashlib.sha256(self.data).hexdigest()
        p = patch.dict(setup.RELEASES, {self.digest: ('v2', 'synthetic test fixture')})
        p.start()
        self.addCleanup(p.stop)

    def test_rejects_malformed_and_unknown_executables(self):
        for data in (b'', b'XEX2', bytes(64), self.data[:31], self.data[:-1] + b'x'):
            with self.subTest(data=data), self.assertRaises(builder.BuildError):
                builder.validate_xex(data)
        data = bytearray(self.data)
        struct.pack_into('>I', data, 28, 0xffffffff)
        with self.assertRaises(builder.BuildError):
            builder.validate_xex(data)

    def test_rejects_extraction_escape_and_symlink(self):
        for path in ('../escape', '/absolute', 'resources/../../escape', 'a\\b'):
            with self.subTest(path=path), self.assertRaises(builder.BuildError):
                builder.safe_destination(self.root, path)
        (self.root / 'link').symlink_to('/tmp', target_is_directory=True)
        with self.assertRaises(builder.BuildError):
            builder.safe_destination(self.root, 'link/escape')

    def test_real_iso_reader_validates_and_extracts(self):
        iso = self.root / 'my game.iso'
        iso.write_bytes(disc_image(self.data))
        release, digest, data, entries = builder.read_assets(iso)
        self.assertEqual((release, digest, data), ('v2', self.digest, self.data))
        entry = next(e for e in entries if e.path == 'resources/test.dat')
        destination = self.root / 'extracted' / entry.path
        with iso.open('rb') as stream:
            xdvdfs.extract(stream, entry, str(destination))
        self.assertEqual(destination.read_bytes(), b'hello')

    def test_iso_rejects_traversal_cycles_and_bounds(self):
        for name, sector, size, attr in (('../escape', 60, 5, 0),
                                         ('loop', 40, 64, xdvdfs.ATTR_DIRECTORY),
                                         ('outside', 1000, 20, 0)):
            image = disc_image(self.data)
            entry = directory_entry(name, sector, size, attr)
            image[40 * 2048:40 * 2048 + 64] = bytes(64)
            image[40 * 2048:40 * 2048 + len(entry)] = entry
            with self.subTest(name=name), self.assertRaises(ValueError):
                xdvdfs.list_entries(io.BytesIO(image))

    def fake_build(self, command, cwd):
        self.commands.append(command)
        if command[:2] == ['cmake', '--build'] and '--target' not in command:
            output = Path(command[2])
            output.mkdir(exist_ok=True)
            (output / 'fracture').touch()
            (output / 'fracture_v2.so').touch()

    def test_build_uses_bundled_sdk_and_writes_config_with_spaces(self):
        source = self.root / 'source'
        source.mkdir()
        (source / 'BUILD-ID').write_text('test-revision')
        game = self.root / 'game with "quotes"'
        game.mkdir()
        (game / 'resources').mkdir()
        (game / 'default.xex').write_bytes(self.data)
        state = self.root / 'state'
        state.mkdir()
        self.commands = []
        with patch.object(builder, 'SOURCE', source), patch.object(builder, 'STATE', state), \
             patch.object(builder, 'run', side_effect=self.fake_build):
            builder.build(game, 2)
            # A repeat must reuse the workspace, never bootstrap the SDK.
            builder.build(game, 2)
        result = json.loads((state / 'last-build.json').read_text())
        config = Path(result['binary']).parent / 'fracture.toml'
        self.assertEqual(json.loads(config.read_text().split(' = ', 1)[1]), str(game))
        self.assertEqual((game / 'default.xex').read_bytes(), self.data)
        self.assertEqual(len(self.commands), 8)
        self.assertTrue(all(command[0] == 'cmake' for command in self.commands))
        self.assertIn('-DCMAKE_PREFIX_PATH=/opt/fracture-sdk', self.commands[0])

    def test_failure_does_not_publish_success(self):
        source = self.root / 'source'
        source.mkdir()
        (source / 'BUILD-ID').write_text('test-revision')
        game = self.root / 'game'
        game.mkdir()
        (game / 'resources').mkdir()
        (game / 'default.xex').write_bytes(self.data)
        state = self.root / 'state'
        state.mkdir()
        with patch.object(builder, 'SOURCE', source), patch.object(builder, 'STATE', state), \
             patch.object(builder, 'run', side_effect=OSError('interrupted build')):
            with self.assertRaises(OSError):
                builder.build(game, 1)
        self.assertFalse((state / 'last-build.json').exists())

    def test_iso_build_overwrites_partial_extraction(self):
        source = self.root / 'source'
        source.mkdir()
        (source / 'BUILD-ID').write_text('test-revision')
        iso = self.root / 'my disc.iso'
        iso.write_bytes(disc_image(self.data))
        state = self.root / 'state'
        state.mkdir()
        partial = state / 'builds/test-revision/v2/game/resources/test.dat'
        partial.parent.mkdir(parents=True)
        partial.write_bytes(b'incomplete')
        self.commands = []
        with patch.object(builder, 'SOURCE', source), patch.object(builder, 'STATE', state), \
             patch.object(builder, 'run', side_effect=self.fake_build):
            builder.build(iso, 1)
        self.assertEqual(partial.read_bytes(), b'hello')
        result = json.loads((state / 'last-build.json').read_text())
        self.assertEqual(Path(result['game']) / 'resources/test.dat', partial)


if __name__ == '__main__':
    unittest.main()
