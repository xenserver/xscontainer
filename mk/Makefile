USE_BRANDING := yes
IMPORT_BRANDING := yes
IMPORT_VERSIONS := yes
include $(B_BASE)/common.mk
include $(B_BASE)/rpmbuild.mk

REPO = $(call git_loc,xscontainer)
RPM_BINDIR = $(RPM_RPMSDIR)/$(DOMAIN0_ARCH_OPTIMIZED)
CSET_NUMBER := $(shell $(shell $(call git_cset_number,xscontainer)); echo $$CSET_NUMBER)
VERSION := $(PLATFORM_VERSION)
RELEASE := $(CSET_NUMBER)

RPMPREFIX := xscontainer-$(VERSION)-$(RELEASE)
RPM := $(RPMPREFIX).noarch.rpm
SRPM := $(RPMPREFIX).src.rpm
SUPP_PACK := $(MY_OUTPUT_DIR)/xscontainer-supp-pack
XSCONTAINER_STAMP := $(MY_OBJ_DIR)/.rpmbuild.stamp

.PHONY: build
build: $(XSCONTAINER_STAMP) $(SUPP_PACK)

.PHONY: $(XSCONTAINER_STAMP)
$(XSCONTAINER_STAMP): $(MY_SOURCES)/MANIFEST
	mkdir -p $(RPM_SRPMSDIR) $(RPM_SOURCESDIR) $(RPM_RPMSDIR) $(MY_OUTPUT_DIR)\
		$(MY_MAIN_PACKAGES)
	cd $(REPO) && git archive --format=tar \
		--prefix=xscontainer-$(PLATFORM_VERSION)/ \
		`cat .git/refs/heads/master` \
        | bzip2 > $(RPM_SOURCESDIR)/xscontainer-$(VERSION)-$(RELEASE).tar.bz2
	REPO=$(REPO) MY_OUTPUT_DIR=$(MY_OUTPUT_DIR) RELEASE=$(RELEASE) \
		VERSION=$(VERSION) $(MAKE) -C $(REPO) bdist_rpm
	mv $(MY_OUTPUT_DIR)/$(RPM) $(MY_MAIN_PACKAGES)
	mv $(MY_OUTPUT_DIR)/$(SRPM) $(RPM_SRPMSDIR)
	touch $@

.PHONY: $(MY_SOURCES)/MANIFEST
$(MY_SOURCES)/MANIFEST: $(MY_SOURCES_DIRSTAMP)
	rm -f $@
	/bin/sh ./srpms-to-manifest xscontainer $(MY_OUTPUT_DIR)/SRPMS > $@

.PHONY: clean
clean:
	rm -f $(OUTPUT)
	$(MAKE) -C $(REPO) clean

.PHONY: $(SUPP_PACK)
$(SUPP_PACK): $(XSCONTAINER_STAMP)
	./make-supp-pack --out $(dir $@) \
	                 --pdn $(PRODUCT_BRAND) \
	                 --pdv $(PRODUCT_VERSION) \
	                 --bld $(CSET_NUMBER) \
	                 --spn $(notdir $@) \
	                 --spd "XSContainer" \
	                 --rxv "6.4.0" \
	                 $(MY_MAIN_PACKAGES)/$(RPM) \
	                 /distros/CentOS/5.10/os/x86_64/CentOS/mkisofs-2.01-10.7.el5.x86_64.rpm
