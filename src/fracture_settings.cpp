// fracture - user settings storage (settings.toml), restart, cvar dump.

#include "fracture_settings.h"

#include "fracture_paths.h"

#include <rex/cvar.h>
#include <rex/filesystem.h>
#include <rex/logging.h>

#include <fmt/format.h>
#include <fmt/ranges.h>
#include <toml++/toml.hpp>

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <cwctype>
#include <fstream>
#include <limits>
#include <string>
#include <string_view>
#include <system_error>
#include <vector>

#if defined(_WIN32)
#include <windows.h>
#elif defined(__linux__)
#include <cerrno>
#include <csignal>
#include <spawn.h>
#include <thread>
#include <unistd.h>
#endif

#if defined(__linux__)
extern char** environ;
#endif

REXCVAR_DEFINE_UINT32(fracture_restart_wait_pid, 0, "Fracture",
                      "Set by the settings menu's restart: wait for this "
                      "process to exit before starting");

namespace fracture::settings {
namespace {

using rex::cvar::FlagEntry;
using rex::cvar::FlagType;

constexpr std::string_view kFileName = "settings.toml";
constexpr std::string_view kHeader =
    "# fracture.exe settings chosen in the in-game settings menu.\n"
    "# Applied after fracture.toml, so values here win over it; command-line\n"
    "# flags still win over both. Delete a line to go back to the default.\n\n";

bool ParseBool(std::string_view text, bool& out) {
  if (text == "true" || text == "1") {
    out = true;
    return true;
  }
  if (text == "false" || text == "0") {
    out = false;
    return true;
  }
  return false;
}

template <typename T>
bool ParseInteger(std::string_view text, T& out) {
  auto [ptr, ec] = std::from_chars(text.data(), text.data() + text.size(), out);
  return ec == std::errc() && ptr == text.data() + text.size();
}

// Values are text in whatever form their writer produced ("60.000000" from
// the cvar macro, "60" from the menu), so compare by value, not by spelling.
bool ValuesEqual(FlagType type, std::string_view a, std::string_view b) {
  if (a == b) {
    return true;
  }
  switch (type) {
    case FlagType::Boolean: {
      bool x = false;
      bool y = false;
      return ParseBool(a, x) && ParseBool(b, y) && x == y;
    }
    case FlagType::Int32:
    case FlagType::Int64:
    case FlagType::Uint32:
    case FlagType::Uint64:
    case FlagType::Double: {
      double x = 0.0;
      double y = 0.0;
      return rex::cvar::ParseDouble(a, x) && rex::cvar::ParseDouble(b, y) && x == y;
    }
    default:
      return false;
  }
}

bool IsDefault(const FlagEntry& entry, std::string_view value) {
  return ValuesEqual(entry.type, value, entry.default_value);
}

// Stores the value with the cvar's own TOML type so the file stays easy to
// edit by hand. LoadConfig turns every value back into text for the setter,
// so a string is a safe fallback for anything else.
bool Assign(toml::table& table, const std::string& name, const FlagEntry* entry,
            std::string_view value) {
  if (!entry) {
    table.insert_or_assign(name, std::string(value));
    return true;
  }
  switch (entry->type) {
    case FlagType::Boolean: {
      bool parsed = false;
      if (!ParseBool(value, parsed)) {
        return false;
      }
      table.insert_or_assign(name, parsed);
      return true;
    }
    case FlagType::Int32:
    case FlagType::Int64:
    case FlagType::Uint32: {
      int64_t parsed = 0;
      if (!ParseInteger(value, parsed)) {
        return false;
      }
      table.insert_or_assign(name, parsed);
      return true;
    }
    case FlagType::Uint64: {
      uint64_t parsed = 0;
      if (!ParseInteger(value, parsed)) {
        return false;
      }
      // TOML integers are signed 64-bit.
      if (parsed > uint64_t(std::numeric_limits<int64_t>::max())) {
        table.insert_or_assign(name, std::string(value));
      } else {
        table.insert_or_assign(name, int64_t(parsed));
      }
      return true;
    }
    case FlagType::Double: {
      double parsed = 0.0;
      if (!rex::cvar::ParseDouble(value, parsed)) {
        return false;
      }
      table.insert_or_assign(name, parsed);
      return true;
    }
    case FlagType::String:
      table.insert_or_assign(name, std::string(value));
      return true;
    case FlagType::Command:
      return false;
  }
  return false;
}

std::string_view TypeName(FlagType type) {
  switch (type) {
    case FlagType::Boolean:
      return "bool";
    case FlagType::Int32:
      return "int32";
    case FlagType::Int64:
      return "int64";
    case FlagType::Uint32:
      return "uint32";
    case FlagType::Uint64:
      return "uint64";
    case FlagType::Double:
      return "double";
    case FlagType::String:
      return "string";
    case FlagType::Command:
      return "command";
  }
  return "?";
}

std::string_view LifecycleName(rex::cvar::Lifecycle lifecycle) {
  switch (lifecycle) {
    case rex::cvar::Lifecycle::kInitOnly:
      return "init_only";
    case rex::cvar::Lifecycle::kHotReload:
      return "live";
    case rex::cvar::Lifecycle::kRequiresRestart:
      return "restart";
  }
  return "?";
}

std::string_view SourceName(rex::cvar::Source source) {
  switch (source) {
    case rex::cvar::Source::kDefault:
      return "default";
    case rex::cvar::Source::kConfig:
      return "config";
    case rex::cvar::Source::kEnvironment:
      return "env";
    case rex::cvar::Source::kCommandLine:
      return "cmdline";
    case rex::cvar::Source::kRuntime:
      return "runtime";
  }
  return "?";
}

std::filesystem::path g_base_config_path;

// Keys the base config sets. An unreadable file sets nothing: the SDK could
// not have applied it either.
toml::table ReadBaseConfig() {
  if (g_base_config_path.empty() || !std::filesystem::exists(g_base_config_path)) {
    return {};
  }
  try {
    return toml::parse_file(g_base_config_path.u8string());
  } catch (const toml::parse_error&) {
    return {};
  }
}

bool IsAscii(const std::filesystem::path& path) {
  const auto& native = path.native();
  return std::all_of(native.begin(), native.end(), [](auto c) { return unsigned(c) < 0x80; });
}

#if defined(_WIN32)
std::filesystem::path ShortPath(const std::filesystem::path& path) {
  const DWORD length = GetShortPathNameW(path.c_str(), nullptr, 0);
  if (length == 0) {
    return {};
  }
  std::wstring buffer(length, L'\0');
  const DWORD written = GetShortPathNameW(path.c_str(), buffer.data(), length);
  if (written == 0 || written >= length) {
    return {};
  }
  buffer.resize(written);
  return std::filesystem::path(buffer);
}
#endif

// rex::cvar::LoadConfig hands path::string() (the ANSI code page) to
// toml++, which reads it as UTF-8, so a file in a folder with non-ASCII
// characters (C:\Users\<name>\Downloads) does not load. Give it an ASCII
// path to the same content then: the 8.3 short name, or a copy in the temp
// folder (by its short name). LoadConfig is still the one to use: it keeps
// command-line flags on top and holds values for plugin cvars until they
// are registered.
bool LoadConfigFile(const std::filesystem::path& path) {
#if defined(_WIN32)
  if (!IsAscii(path)) {
    const auto short_path = ShortPath(path);
    if (!short_path.empty() && IsAscii(short_path)) {
      rex::cvar::LoadConfig(short_path);
      return true;
    }
    wchar_t temp[MAX_PATH + 1] = {};
    const DWORD length = GetTempPathW(MAX_PATH + 1, temp);
    const auto temp_dir = length ? ShortPath(std::filesystem::path(temp)) : std::filesystem::path();
    if (!temp_dir.empty() && IsAscii(temp_dir)) {
      const auto copy = temp_dir / fmt::format("fracture-{}-config.toml", GetCurrentProcessId());
      std::error_code ec;
      std::filesystem::copy_file(path, copy, std::filesystem::copy_options::overwrite_existing,
                                 ec);
      if (!ec) {
        rex::cvar::LoadConfig(copy);
        std::filesystem::remove(copy, ec);
        return true;
      }
    }
    REXLOG_WARN("Settings: cannot load {}: the SDK cannot open files in this folder",
                PathText(path));
    return false;
  }
#endif
  rex::cvar::LoadConfig(path);
  return true;
}

// Keeps one cvar per line in the dump.
std::string OneLine(std::string text) {
  std::replace(text.begin(), text.end(), '\n', ' ');
  std::replace(text.begin(), text.end(), '\t', ' ');
  return text;
}

}  // namespace

std::filesystem::path Path() {
  return rex::filesystem::GetExecutableFolder() / kFileName;
}

void Load(const std::filesystem::path& base_config_path) {
  g_base_config_path = base_config_path;
  // The SDK's own load of the base config fails in such a folder (see
  // LoadConfigFile). Its logging cvars are applied by now; the rest still
  // matters.
  if (!IsAscii(base_config_path) && std::filesystem::exists(base_config_path)) {
    LoadConfigFile(base_config_path);
  }
  const auto path = Path();
  if (!std::filesystem::exists(path)) {
    return;
  }
  if (LoadConfigFile(path)) {
    REXLOG_INFO("Settings: applied {}", PathText(path));
  }
}

bool Save(const std::vector<std::pair<std::string, std::string>>& changes) {
  const auto path = Path();
  toml::table table;
  if (std::filesystem::exists(path)) {
    try {
      table = toml::parse_file(path.u8string());
    } catch (const toml::parse_error& err) {
      // Keep the broken file for the user instead of silently dropping it.
      auto backup = path;
      backup += ".bad";
      std::error_code ec;
      std::filesystem::rename(path, backup, ec);
      REXLOG_WARN("Settings: {} is not valid TOML ({}), moved it to {}", PathText(path),
                  err.description(), PathText(backup));
    }
  }

  const toml::table base_config = ReadBaseConfig();
  size_t applied = 0;
  for (const auto& [name, value] : changes) {
    const FlagEntry* entry = rex::cvar::GetFlagInfo(name);
    if (entry && IsDefault(*entry, value) && !base_config.contains(name)) {
      table.erase(name);
    } else if (!Assign(table, name, entry, value)) {
      REXLOG_WARN("Settings: not saving {} = '{}' (not a valid value)", name, value);
      continue;
    }
    ++applied;
  }

  // Write next to the file and swap it in, so a crash mid-write cannot leave
  // a truncated settings.toml behind.
  auto temp = path;
  temp += ".tmp";
  {
    std::ofstream out(temp, std::ios::binary | std::ios::trunc);
    out << kHeader << table << '\n';
    if (!out) {
      REXLOG_ERROR("Settings: failed to write {}", PathText(temp));
      return false;
    }
  }
  std::error_code ec;
  std::filesystem::rename(temp, path, ec);
  if (ec) {
    REXLOG_ERROR("Settings: failed to replace {}: {}", PathText(path), ec.message());
    return false;
  }
  REXLOG_INFO("Settings: saved {} change(s) to {}", applied, PathText(path));
  return true;
}

bool SameValue(std::string_view name, std::string_view a, std::string_view b) {
  const FlagEntry* entry = rex::cvar::GetFlagInfo(name);
  return entry ? ValuesEqual(entry->type, a, b) : a == b;
}

#if defined(_WIN32)

namespace {
constexpr std::wstring_view kWaitFlag = L" --fracture_restart_wait_pid=";
constexpr std::wstring_view kReleaseFlag = L" --fracture_game_release=";
constexpr DWORD kRestartWaitMs = 20000;

// Removes every `flag`<value> an earlier restart appended (always in exactly
// this form, the value up to the next space).
void EraseFlag(std::wstring& command_line, std::wstring_view flag) {
  for (size_t pos; (pos = command_line.find(flag)) != std::wstring::npos;) {
    size_t end = pos + flag.size();
    while (end < command_line.size() && command_line[end] != L' ') {
      ++end;
    }
    command_line.erase(pos, end - pos);
  }
}
}  // namespace

bool StartRestartedProcess(std::string_view game_release) {
  wchar_t exe_path[MAX_PATH] = {};
  const DWORD length = GetModuleFileNameW(nullptr, exe_path, MAX_PATH);
  if (length == 0 || length == MAX_PATH) {
    REXLOG_ERROR("Restart: could not resolve the executable path");
    return false;
  }

  // The original command line as typed, minus the flags an earlier restart
  // appended.
  std::wstring command_line = GetCommandLineW();
  EraseFlag(command_line, kWaitFlag);
  if (!game_release.empty()) {
    EraseFlag(command_line, kReleaseFlag);
    command_line += kReleaseFlag;
    command_line.append(game_release.begin(), game_release.end());
  }
  command_line += kWaitFlag;
  command_line += std::to_wstring(GetCurrentProcessId());

  STARTUPINFOW startup_info{};
  startup_info.cb = sizeof(startup_info);
  PROCESS_INFORMATION process_info{};
  if (!CreateProcessW(exe_path, command_line.data(), nullptr, nullptr, FALSE, 0, nullptr,
                      nullptr, &startup_info, &process_info)) {
    REXLOG_ERROR("Restart: CreateProcess failed ({})", GetLastError());
    return false;
  }
  CloseHandle(process_info.hThread);
  CloseHandle(process_info.hProcess);
  REXLOG_INFO("Restart: started process {}", process_info.dwProcessId);
  return true;
}

void WaitForPreviousProcess() {
  const uint32_t pid = REXCVAR_GET(fracture_restart_wait_pid);
  if (pid == 0) {
    return;
  }
  // A missing process has already exited; a timeout means it hangs on
  // shutdown, and starting anyway beats never starting.
  HANDLE process = OpenProcess(SYNCHRONIZE, FALSE, pid);
  if (process) {
    WaitForSingleObject(process, kRestartWaitMs);
    CloseHandle(process);
  }
  // Back to the default, so a config save from this process (the F4
  // overlay's SaveConfig writes every non-default cvar) cannot persist the
  // pid and make every later start wait on it.
  REXCVAR_SET(fracture_restart_wait_pid, 0);
}

#elif defined(__linux__)

namespace {
constexpr auto kRestartWait = std::chrono::seconds(20);
constexpr auto kRestartPoll = std::chrono::milliseconds(10);

bool IsRestartArgument(std::string_view arg, std::string_view name) {
  return arg.starts_with(name) && (arg.size() == name.size() || arg[name.size()] == '=');
}

std::vector<std::string> CurrentArguments() {
  std::ifstream input("/proc/self/cmdline", std::ios::binary);
  std::vector<std::string> arguments;
  std::string argument;
  char byte = 0;
  while (input.get(byte)) {
    if (byte == '\0') {
      arguments.push_back(std::move(argument));
      argument.clear();
    } else {
      argument.push_back(byte);
    }
  }
  if (!argument.empty()) {
    arguments.push_back(std::move(argument));
  }
  return arguments;
}

bool ProcessIsZombie(uint32_t pid) {
  std::ifstream stat(fmt::format("/proc/{}/stat", pid));
  std::string line;
  if (!std::getline(stat, line)) {
    return false;
  }
  const size_t name_end = line.rfind(')');
  return name_end != std::string::npos && name_end + 2 < line.size() && line[name_end + 2] == 'Z';
}
}  // namespace

bool StartRestartedProcess(std::string_view game_release) {
  std::array<char, 4096> exe_buffer{};
  const ssize_t length = readlink("/proc/self/exe", exe_buffer.data(), exe_buffer.size() - 1);
  if (length <= 0 || size_t(length) >= exe_buffer.size() - 1) {
    REXLOG_ERROR("Restart: could not resolve the executable path: {}", std::strerror(errno));
    return false;
  }
  const std::string exe_path(exe_buffer.data(), size_t(length));
  std::vector<std::string> arguments = CurrentArguments();
  if (arguments.empty()) {
    arguments.push_back(exe_path);
  } else {
    arguments[0] = exe_path;
  }
  std::erase_if(arguments, [](const std::string& arg) {
    return IsRestartArgument(arg, "--fracture_restart_wait_pid");
  });
  if (!game_release.empty()) {
    std::erase_if(arguments, [](const std::string& arg) {
      return IsRestartArgument(arg, "--fracture_game_release");
    });
    arguments.push_back(fmt::format("--fracture_game_release={}", game_release));
  }
  arguments.push_back(fmt::format("--fracture_restart_wait_pid={}", getpid()));

  std::vector<char*> argv;
  argv.reserve(arguments.size() + 1);
  for (std::string& argument : arguments) {
    argv.push_back(argument.data());
  }
  argv.push_back(nullptr);

  pid_t child = 0;
  const int spawn_error = posix_spawn(&child, exe_path.c_str(), nullptr, nullptr,
                                      argv.data(), environ);
  if (spawn_error != 0) {
    REXLOG_ERROR("Restart: could not start {}: {}", exe_path, std::strerror(spawn_error));
    return false;
  }
  REXLOG_INFO("Restart: started process {}", child);
  return true;
}

void WaitForPreviousProcess() {
  const uint32_t pid = REXCVAR_GET(fracture_restart_wait_pid);
  if (pid == 0) {
    return;
  }
  const auto deadline = std::chrono::steady_clock::now() + kRestartWait;
  while (std::chrono::steady_clock::now() < deadline) {
    if ((kill(pid_t(pid), 0) != 0 && errno == ESRCH) || ProcessIsZombie(pid)) {
      break;
    }
    std::this_thread::sleep_for(kRestartPoll);
  }
  REXCVAR_SET(fracture_restart_wait_pid, 0);
}

#else

bool StartRestartedProcess(std::string_view game_release) {
  (void)game_release;
  REXLOG_ERROR("Restart: not implemented on this platform");
  return false;
}

void WaitForPreviousProcess() {}

#endif

bool DumpCvars(const std::filesystem::path& path) {
  std::ofstream out(path, std::ios::binary | std::ios::trunc);
  if (!out) {
    return false;
  }
  auto names = rex::cvar::ListFlags();
  std::sort(names.begin(), names.end());
  out << "name\ttype\tlifecycle\tsource\tcategory\tdefault\tcurrent\tconstraints\tdescription\n";
  for (const auto& name : names) {
    const FlagEntry* entry = rex::cvar::GetFlagInfo(name);
    if (!entry) {
      continue;
    }
    std::string constraints;
    const auto& c = entry->constraints;
    if (c.min) {
      constraints += fmt::format("min={} ", *c.min);
    }
    if (c.max) {
      constraints += fmt::format("max={} ", *c.max);
    }
    if (!c.allowed_values.empty()) {
      constraints += "allowed=" + fmt::format("{}", fmt::join(c.allowed_values, "|")) + " ";
    }
    if (c.custom_validator) {
      constraints += "validator ";
    }
    if (entry->is_debug_only) {
      constraints += "debug_only ";
    }
    const std::string current = entry->type == FlagType::Command ? "" : entry->getter();
    out << entry->name << '\t' << TypeName(entry->type) << '\t'
        << LifecycleName(entry->lifecycle) << '\t' << SourceName(entry->source) << '\t'
        << entry->category << '\t' << OneLine(entry->default_value) << '\t' << OneLine(current)
        << '\t' << constraints << '\t' << OneLine(entry->description) << '\n';
  }
  return bool(out);
}

}  // namespace fracture::settings
