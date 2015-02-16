USE_BRANDING := yes
IMPORT_BRANDING := yes
IMPORT_VERSIONS := yes
include $(B_BASE)/common.mk
include $(B_BASE)/rpmbuild.mk

REPO = $(call git_loc,xscontainer)
RPM_BINDIR = $(RPM_RPMSDIR)/$(DOMAIN0_ARCH_OPTIMIZED)
CSET_NUMBER := $(shell $(shell $(call git_cset_number,xscontainer)); echo $$CSET_NUMBER)
VERSION := $(PRODUCT_VERSION)
RELEASE := $(CSET_NUMBER)

COMPLETE_VERSION := $(VERSION)-$(RELEASE)


RPMPREFIX := xscontainer-$(COMPLETE_VERSION)
RPM := $(RPMPREFIX).noarch.rpm
SRPM := $(RPMPREFIX).src.rpm
SUPP_PACK := $(MY_OUTPUT_DIR)/xscontainer-$(COMPLETE_VERSION)
SUPP_PACK_SOURCES := $(MY_OUTPUT_DIR)/xscontainer-sources-$(COMPLETE_VERSION).iso
XSCONTAINER_STAMP := $(MY_OBJ_DIR)/.rpmbuild.stamp


# packages installed on dom0
DOM0_RPMS :=
# source packages
DOM0_SRPMS  :=
# source packages compiled and installed on dom0
DOM0_BUILD_SRPMS :=

DOM0_RPMS += /distros/CentOS/5.10/os/$(DOMAIN0_ARCH)/CentOS/mkisofs-2.01-10.7.el5.$(DOMAIN0_ARCH).rpm
DOM0_SRPMS += /distros/CentOS/5.10/os/SRPMS/cdrtools-2.01-10.7.el5.src.rpm
DOM0_RPMS += /distros/CentOS/5.10/os/$(DOMAIN0_ARCH)/CentOS/gmp-4.1.4-10.el5.$(DOMAIN0_ARCH).rpm
DOM0_SRPMS += /distros/CentOS/5.10/os/SRPMS/gmp-4.1.4-10.el5.src.rpm
DOM0_RPMS += /usr/src/redhat/RPMS/noarch/python-paramiko-1.7.6-1.noarch.rpm
DOM0_SRPMS += /distfiles/xscontainer/epel/2015-02-13/5/SRPMS/python-paramiko-1.7.6-1.el5.src.rpm
DOM0_RPMS += /usr/src/redhat/RPMS/$(DOMAIN0_ARCH)/python-crypto-2.0.1-5.$(DOMAIN0_ARCH).rpm
DOM0_SRPMS += /distfiles/xscontainer/epel/2015-02-13/5/SRPMS/python-crypto-2.0.1-5.el5.src.rpm
DOM0_BUILD_SRPMS += /distfiles/xscontainer/epel/2015-02-13/5/SRPMS/python-crypto-2.0.1-5.el5.src.rpm
DOM0_BUILD_SRPMS += /distfiles/xscontainer/epel/2015-02-13/5/SRPMS/python-paramiko-1.7.6-1.el5.src.rpm

.PHONY: build
build: $(XSCONTAINER_STAMP) $(SUPP_PACK)

.PHONY: $(XSCONTAINER_STAMP)
$(XSCONTAINER_STAMP): $(MY_SOURCES)/MANIFEST
	mkdir -p $(RPM_SRPMSDIR) $(RPM_SOURCESDIR) $(RPM_RPMSDIR) $(MY_OUTPUT_DIR)\
		$(MY_MAIN_PACKAGES)
	cd $(REPO) && \
	    git archive --format=tar --prefix=xscontainer-$(PLATFORM_VERSION)/ HEAD\
        | bzip2 > $(RPM_SOURCESDIR)/xscontainer-$(COMPLETE_VERSION).tar.bz2
	REPO=$(REPO) MY_OUTPUT_DIR=$(MY_OUTPUT_DIR) RELEASE=$(RELEASE) \
		VERSION=$(VERSION) $(MAKE) -C $(REPO) bdist_rpm
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
	mkdir -p $(MY_OBJ_DIR)/ISO-SOURCES
	cp -f $(MY_OUTPUT_DIR)/$(SRPM) $(MY_OBJ_DIR)/ISO-SOURCES/
	cp -f $(DOM0_SRPMS) $(MY_OBJ_DIR)/ISO-SOURCES/
	mkisofs -A "Citrix" -V "xscontainer" -J -joliet-long -r -o $(SUPP_PACK_SOURCES) $(MY_OBJ_DIR)/ISO-SOURCES
	@for f in $(DOM0_BUILD_SRPMS); do rpmbuild --rebuild $$f; done
	./make-supp-pack --out $(dir $@) \
	                 --pdn $(PRODUCT_BRAND) \
	                 --pdv $(VERSION) \
	                 --bld $(RELEASE) \
	                 --spn $(notdir $@) \
	                 --spd "XSContainer" \
	                 --rxv "6.5" \
	                 $(MY_OUTPUT_DIR)/$(RPM) \
	                 $(DOM0_RPMS)
