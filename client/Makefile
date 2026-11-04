CC ?= cc
AR ?= ar
PKG_CONFIG ?= pkg-config
CPPFLAGS += -Iinclude -I../protocol/include $(shell $(PKG_CONFIG) --cflags xcb)
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Wpedantic -Werror
SOURCES := src/connection.c src/devices.c
OBJECTS := $(SOURCES:.c=.o)

.PHONY: all clean check
all: libxaverius-client.a

libxaverius-client.a: $(OBJECTS)
	$(AR) rcs $@ $^

src/%.o: src/%.c src/internal.h include/xaverius_client.h ../protocol/include/xaverius_proto.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -c -o $@ $<

check: all
	@echo "client prototype compiled successfully"

clean:
	rm -f $(OBJECTS) libxaverius-client.a
