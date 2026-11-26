Name:           d11ctl
Version:        0.1.0
Release:        1%{?dist}
Summary:        Research toolkit for porting iOS 16 to iPhone 7 Plus (D11/D111)
License:        GPL-3.0-or-later
URL:            https://github.com/hurmichov/ios16-d11
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3-pip
BuildRequires:  python3-wheel
BuildRequires:  pyproject-rpm-macros

Requires:       python3 >= 3.9
Requires:       libimobiledevice-utils
Requires:       usbmuxd
Requires:       libirecovery-utils
Requires:       idevicerestore
Recommends:     libplist-utils

%description
d11ctl — device detection, IPSW handling, compatibility analysis, boot log
monitoring, diagnostics and stock recovery for the experimental iOS 16 port
to iPhone 7 Plus (A10 Fusion, T8010). Ships no Apple binaries: firmware is
downloaded from Apple servers on the user's machine.

%prep
%autosetup -n %{name}-%{version}

%generate_buildrequires
cd tool
%pyproject_buildrequires

%build
cd tool
%pyproject_wheel

%install
cd tool
%pyproject_install
%pyproject_save_files d11ctl
install -Dm0644 ../firmware/rp2350/60-d11diag.rules %{buildroot}%{_udevrulesdir}/60-d11diag.rules
install -Dm0644 recipes/evt1-research.json %{buildroot}%{_datadir}/%{name}/recipes/evt1-research.json

%check
cd tool
%{py3_test_envvars} %{python3} -m pytest -q tests || :

%files -f %{pyproject_files}
%license LICENSE
%doc README.md docs
%{_bindir}/d11ctl
%{_udevrulesdir}/60-d11diag.rules
%{_datadir}/%{name}/

%changelog
* Thu Nov 26 2026 d11ctl developers - 0.1.0-1
- EVT0: initial package
