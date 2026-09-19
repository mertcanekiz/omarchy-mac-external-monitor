#!/usr/bin/env python3
"""Compare both initramfs images, module identities, and compiled DT routing."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'artifacts/thunderbolt-dpin'
FDTGET = ROOT / 'artifacts/thunderbolt-toolchain/root/usr/bin/fdtget'
FDT_ENV = dict(os.environ, LD_LIBRARY_PATH=str(FDTGET.parent.parent / 'lib'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(root):
    return {str(p.relative_to(root)): ('symlink', str(p.readlink())) if p.is_symlink()
            else ('file', sha(p)) for p in root.rglob('*') if p.is_file() or p.is_symlink()}


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', choices=['v1', 'v2'], default='v1')
    args = parser.parse_args()
    suffix = '' if args.revision == 'v1' else '-v2'
    name = 'thunderbolt-dpin' + suffix
    OUT = ROOT / ('artifacts/' + name)
    with tempfile.TemporaryDirectory(prefix='verify-', dir=OUT) as temporary:
        base = Path(temporary)
        trees = []
        for label, image in [('baseline', ROOT / 'artifacts/initramfs-thunderbolt-test.img'),
                             ('candidate', OUT / f'initramfs-{name}.img')]:
            directory = base / label
            directory.mkdir()
            subprocess.run(['lsinitcpio', '-x', str(image)], cwd=directory,
                           check=True, stdout=subprocess.DEVNULL)
            trees.append(tree(directory))
        old, new = trees
        changed = sorted(p for p in old.keys() & new.keys() if old[p] != new[p])
        added, removed = sorted(new.keys() - old.keys()), sorted(old.keys() - new.keys())
        module_path = 'usr/lib/modules/7.2.2-thunderbolt-test+/kernel/drivers/gpu/drm/apple/appledrm.ko'
        if new.get(module_path) != ('file', sha(OUT / 'appledrm.ko')):
            raise SystemExit('Embedded appledrm does not match the candidate.')
        if [p for p in changed if '.ko' in p] != [module_path]:
            raise SystemExit(f'Unexpected module content changes: {changed}')
        if any('.ko' in p for p in added + removed):
            raise SystemExit(f'Unexpected module set change: added={added}, removed={removed}')
        if new.get('hooks/asahi') != old.get('hooks/asahi'):
            raise SystemExit('Asahi hook changed.')
        # These files are sourced by early userspace. Compare hook ordering
        # exactly. The existing apple_hid_modules.conf conditional detects
        # these two modules after booting/installing the new kernel; permit
        # early loading only if their bytes already match the baseline.
        configs = [(base / label / 'config').read_text() for label in ('baseline', 'candidate')]
        def parse_config(text):
            return dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
        before_config, after_config = map(parse_config, configs)
        before_modules = before_config.pop('MODULES', '').strip('"').split()
        after_modules = after_config.pop('MODULES', '').strip('"').split()
        added_modules = set(after_modules) - set(before_modules)
        allowed_early_loads = {'hid_apple': 'hid-apple.ko',
                               'hid_magicmouse': 'hid-magicmouse.ko'}
        if (before_config != after_config or
                set(before_modules) - set(after_modules) or
                added_modules - allowed_early_loads.keys()):
            raise SystemExit(f'Unexpected runtime initramfs configuration change: {configs}')
        for name in added_modules:
            path = ('usr/lib/modules/7.2.2-thunderbolt-test+/kernel/drivers/hid/'
                    + allowed_early_loads[name])
            if path not in old or old[path] != new.get(path):
                raise SystemExit(f'Early-loaded HID module changed or was absent: {path}')
        if set(changed) - {'config', module_path} or set(added) - {'early_cpio'} or removed:
            raise SystemExit('Unexpected initramfs file changes outside the experiment.')
        report = {'changed': changed, 'added': added, 'removed': removed,
                  'identical_entries': len(old.keys() & new.keys()) - len(changed),
                  'only_module_changed': module_path,
                  'runtime_config_before': configs[0], 'runtime_config_after': configs[1],
                  'hook_order_matches': True,
                  'additional_early_loads_of_unchanged_modules': sorted(added_modules)}

    def get(node, prop, fmt='x'):
        return subprocess.check_output([str(FDTGET), '-t', fmt,
            str(OUT / 't8103-j313.dtb'), node, prop], text=True, env=FDT_ENV).strip()
    dcp = '/soc/dcp@271c00000'
    assert get(dcp, 'status', 's') == 'okay'
    assert get(dcp, 'apple,dptx-core') == '1'
    assert get(dcp, 'apple,dptx-phy') == '1'
    assert get(dcp, 'mux-index') == '0'
    mux = get(dcp, 'mux-controls').split()
    assert mux == [get('/soc/mux@50304c000', 'phandle'), '1']
    assert len(get('/soc/display-subsystem', 'iommus').split()) == 12
    if args.revision == 'v2':
        assert get(dcp + '/piodma', 'iommus').split() == [
            get('/soc/iommu@271304000', 'phandle'), '4', '0', '0', '0', 'fc000000']
    assert get('/aliases', 'dcpext', 's') == dcp
    properties = subprocess.check_output([str(FDTGET), '-p', str(OUT / 't8103-j313.dtb'), dcp], text=True, env=FDT_ENV).splitlines()
    assert 'phys' not in properties and 'apple,tbt-dpin-test' in properties
    report['dt_checks'] = 'external DCP enabled; ATC1/core1; crossbar DPIN0/dispext0; correct 5-cell IOMMU specifiers; no physical DP PHY'
    report['vermagic'] = subprocess.check_output(['modinfo', '-F', 'vermagic', str(OUT / 'appledrm.ko')], text=True).strip()
    assert report['vermagic'] == '7.2.2-thunderbolt-test+ SMP preempt mod_unload aarch64'
    report['revision'] = args.revision
    (ROOT / f'reports/thunderbolt/dpin{suffix}-verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
