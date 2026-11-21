# Build-time container only. End users do not need Docker, root, or network.
FROM ubuntu:24.04
ARG DEBIAN_FRONTEND=noninteractive
ARG BUILD_JOBS=2
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg git cmake ninja-build build-essential g++-13 \
    python3 python3-tk proot busybox-static autoconf automake libtool pkg-config \
    libgtk-3-dev libx11-xcb-dev libxss-dev libvulkan-dev glslang-tools \
    libwayland-dev libwayland-bin wayland-protocols libxkbcommon-dev libdecor-0-dev \
    libasound2-dev libpulse-dev libpipewire-0.3-dev mesa-vulkan-drivers \
    libgl1-mesa-dri libglx-mesa0 fonts-dejavu-core xz-utils unzip zip \
    && curl -fsSL https://apt.llvm.org/llvm-snapshot.gpg.key \
       | gpg --dearmor -o /usr/share/keyrings/llvm.gpg \
    && echo 'deb [signed-by=/usr/share/keyrings/llvm.gpg] https://apt.llvm.org/noble/ llvm-toolchain-noble-20 main' \
       > /etc/apt/sources.list.d/llvm.list \
    && apt-get update && apt-get install -y --no-install-recommends clang-20 lld-20 \
    && rm -rf /var/lib/apt/lists/*
ENV CC=clang-20 CXX=clang++-20
RUN git clone --branch v0.10.0 --depth 1 --recurse-submodules --shallow-submodules --jobs 4 \
      https://github.com/rexglue/rexglue-sdk.git /opt/rexglue-source \
    && test "$(git -C /opt/rexglue-source rev-parse HEAD)" = f5337cdc947ff6d4c4196737e2c807a48f2a1fc2 \
    && cmake -S /opt/rexglue-source -B /tmp/sdk-build -G Ninja \
      -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang-20 -DCMAKE_CXX_COMPILER=clang++-20 \
      -DCMAKE_INSTALL_PREFIX=/opt/fracture-sdk -DREXGLUE_USE_D3D12=OFF \
      -DREXGLUE_USE_VULKAN=ON -DREXGLUE_BUILD_TESTS=OFF \
    && cmake --build /tmp/sdk-build --target install --parallel "${BUILD_JOBS}" \
    && rm -rf /tmp/sdk-build \
    && find /opt/rexglue-source -name .git -prune -exec rm -rf '{}' +
# Explicit allowlist: never COPY the checkout, local generated code, XEXs, or ISOs.
COPY CMakeLists.txt CMakePresets.json fracture_v1_manifest.toml fracture_v2_manifest.toml README.md UPSTREAM.md /opt/fracture-source/
COPY cmake/ /opt/fracture-source/cmake/
COPY config/ /opt/fracture-source/config/
COPY src/ /opt/fracture-source/src/
COPY tools/setup.py tools/xdvdfs.py /opt/fracture-source/tools/
COPY packaging/appimage/builder.py packaging/appimage/launcher.py /opt/fracture-builder/
COPY packaging/appimage/smoke/ /opt/fracture-builder/smoke/
ARG SOURCE_ID
RUN test -n "${SOURCE_ID}" && printf '%s\n' "${SOURCE_ID}" > /opt/fracture-source/BUILD-ID \
    && mkdir -p /work /run /media /mnt \
    && python3 -m py_compile /opt/fracture-builder/*.py \
    && clang++-20 --version && cmake --version && ninja --version \
    && /opt/fracture-sdk/bin/rexglue --version \
    && dpkg-query -W > /opt/fracture-builder/PACKAGES.txt
WORKDIR /work
