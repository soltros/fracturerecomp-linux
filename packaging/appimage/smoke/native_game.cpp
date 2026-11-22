#include <rex/filesystem.h>
#include <cassert>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
#include <thread>

int main(int argc, char** argv) {
  const auto binary = rex::filesystem::GetExecutablePath();
  assert(binary.filename() == "fracture");
  assert(std::filesystem::exists(binary));
  assert(argc == 2);
  assert(std::string(argv[1]) == std::string("--game_data_root=") + std::getenv("FRACTURE_SMOKE_GAME"));
  std::ifstream status("/proc/self/status");
  std::string line;
  while (std::getline(status, line)) {
    if (line.starts_with("TracerPid:")) assert(std::stoi(line.substr(10)) == 0);
  }
  if (const char* data = std::getenv("RECOMPLAUNCHER_DATA")) {
    assert(std::string(data) != "/work");
    assert(std::filesystem::is_directory(data));
  }
  int count = 0;
  std::thread worker([&] { for (int i = 0; i < 10000; ++i) ++count; });
  worker.join();
  assert(count == 10000);
  std::ofstream(std::getenv("FRACTURE_SMOKE_LOG")) << "native game launched\n";
}
