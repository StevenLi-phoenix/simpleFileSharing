## Simple C++ build for server and CLI

CXX ?= c++
CXXFLAGS ?= -std=c++20 -O2 -Wall -Wextra -pedantic -pthread
INC := -Isrc -Ithird_party

BIN_DIR := bin
SRC := src
SERVER := $(BIN_DIR)/server

SERVER_SRC := $(SRC)/main.cpp $(SRC)/storage.cpp

.PHONY: all server run clean

all: server

server: $(SERVER)

$(BIN_DIR):
	@mkdir -p $(BIN_DIR)

$(SERVER): $(SERVER_SRC) | $(BIN_DIR)
	$(CXX) $(CXXFLAGS) $(INC) $^ -o $@

run: $(SERVER)
	./$(SERVER)

clean:
	rm -rf $(BIN_DIR)

# Notes:
# - The server compiles without external deps. If you place cpp-httplib in third_party/httplib.h,
#   it will enable the HTTP endpoints automatically.
# - mapping.json and resources/ are reused from the Python app.
