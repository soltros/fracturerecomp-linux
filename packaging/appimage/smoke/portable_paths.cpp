#include "fracture_paths.h"
#include "fracture_settings.h"

#include <rex/filesystem.h>
#include <cstdlib>

int main() {
  unsetenv("RECOMPLAUNCHER_DATA");
  if (!fracture::LauncherDataRoot().empty()) return 1;
  if (fracture::settings::Path() != rex::filesystem::GetExecutableFolder() / "settings.toml") return 2;
  setenv("RECOMPLAUNCHER_DATA", "/work/portable-path-test", 1);
  if (fracture::settings::Path() != "/work/portable-path-test/settings.toml") return 3;
  setenv("RECOMPLAUNCHER_DATA", "relative-path", 1);
  if (!fracture::LauncherDataRoot().empty()) return 4;
  unsetenv("RECOMPLAUNCHER_DATA");
  return 0;
}
