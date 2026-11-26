Name:           halcyon
Version:        0.1.0
Release:        1%{?dist}
Summary:        Research toolkit for porting iOS 16 to iPhone 7 Plus (A10 Fusion)
License:        MIT
URL:            https://github.com/hurmichov/ios16-d11
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-pytest
BuildRequires:  pyproject-rpm-macros

Requires:       python3 >= 3.11
Requires:       libimobiledevice-utils
Requires:       libirecovery-utils
Requires:       usbmuxd
Recommends:     idevicerestore
Recommends:     lzfse
Recommends:     apfs-fuse

%description
Halcyon detects iPhone 7 Plus devices (normal/recovery/DFU), inspects and compares
IPSW firmware (BuildManifest, IM4P, DeviceTree, XNU), runs reproducible build profiles
in dry-run by default, classifies boot logs from a serial adapter and wraps stock
iOS 15 backup/restore. It ships no Apple binaries.

%prep
%autosetup -n %{name}-%{version}

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files halcyon
install -Dm0644 profiles/d11-ios16.toml %{buildroot}%{_datadir}/%{name}/profiles/d11-ios16.toml
install -Dm0644 packaging/60-halcyon-diag.rules %{buildroot}%{_udevrulesdir}/60-halcyon-diag.rules

%check
%pytest -q tests

%files -f %{pyproject_files}
%license LICENSE
%doc README.md docs/
%{_bindir}/halcyon
%{_datadir}/%{name}/
%{_udevrulesdir}/60-halcyon-diag.rules

%changelog
* Thu Nov 26 2026 Halcyon contributors - 0.1.0-1
- EVT0: initial toolkit skeleton
