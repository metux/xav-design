CC ?= cc
AR ?= ar
PKG_CONFIG ?= pkg-config
CPPFLAGS += -Iinclude -I../protocol/include $(shell $(PKG_CONFIG) --cflags xcb)
CFLAGS ?= -O2 -g
CFLAGS += -std=c11 -Wall -Wextra -Wpedantic -Werror
SOURCES := src/connection.c src/devices.c src/xge.c src/events.c
OBJECTS := $(SOURCES:.c=.o)

.PHONY: all clean check
all: libxaverius-client.a

libxaverius-client.a: $(OBJECTS)
	$(AR) rcs $@ $^

src/%.o: src/%.c src/internal.h include/xaverius_client.h ../protocol/include/xaverius.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -c -o $@ $<

tests/test_events: tests/test_events.c libxaverius-client.a
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ $< libxaverius-client.a $(shell $(PKG_CONFIG) --libs xcb)

check: all tests/test_events
	./tests/test_events
	@echo "client prototype and event decoder tests passed"

clean:
	rm -f $(OBJECTS) libxaverius-client.a tests/test_events
