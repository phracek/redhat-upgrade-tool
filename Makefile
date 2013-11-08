PYTHON=python
VERSION=0.7.3

all: build

SUBDIRS := systemd man
$(SUBDIRS):
	$(MAKE) -C $@

INSTALL_TARGETS = $(SUBDIRS:%=install-%)
$(INSTALL_TARGETS):
	$(MAKE) -C $(@:install-%=%) install

CLEAN_TARGETS = $(SUBDIRS:%=clean-%)
$(CLEAN_TARGETS):
	$(MAKE) -C $(@:clean-%=%) clean

build: $(SUBDIRS)
	$(PYTHON) setup.py build

install: all $(INSTALL_TARGETS)
	$(PYTHON) setup.py install --skip-build --root $(DESTDIR)/

clean: $(CLEAN_TARGETS)
	$(PYTHON) setup.py clean
	rm -rf build
	rm -f $(ARCHIVE)

ARCHIVE = redhat-upgrade-tool-$(VERSION).tar.xz
archive: $(ARCHIVE)
redhat-upgrade-tool-$(VERSION).tar.xz:
	git archive --format=tar --prefix=redhat-upgrade-tool-$(VERSION)/ HEAD \
	  | xz -c > $@ || rm $@

.PHONY: all archive install clean
.PHONY: $(SUBDIRS) $(INSTALL_TARGETS) $(CLEAN_TARGETS)
