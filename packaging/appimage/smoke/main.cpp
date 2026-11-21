#include <rex/logging.h>

int main(int argc, char**) {
  // Retain a reference to the SDK so linking and loading its shared runtime
  // are both exercised, without initializing a game or a desktop window.
  if (argc == 12345) {
    REXLOG_INFO("Fracture offline SDK link test");
  }
  return 0;
}
