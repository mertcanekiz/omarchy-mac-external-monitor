#!/usr/bin/env python3
"""Validate built artifacts without loading modules or modifying boot files."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent
KERNEL = "7.1.13-3-1-ARCH"


def run(*args):
    return subprocess.check_output(args, text=True, cwd=ROOT).strip()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    with tempfile.TemporaryDirectory(prefix="verify-initramfs-", dir=ROOT / "artifacts") as temporary:
        subprocess.run(
            ["lsinitcpio", "-x", str(ROOT / "artifacts/initramfs-display-test.img")],
            cwd=temporary, check=True, stdout=subprocess.DEVNULL,
        )
        verify(Path(temporary))


def verify(unpacked):
    checks = []
    for name in ("tps6598x-core", "tps6598x"):
        built = ROOT / f"artifacts/tipd/{name}.ko"
        inside = unpacked / f"usr/lib/modules/{KERNEL}/kernel/drivers/usb/typec/tipd/{name}.ko"
        assert sha(built) == sha(inside), f"Wrong initramfs copy: {name}"
        assert run("modinfo", "-F", "vermagic", str(built)) == f"{KERNEL} SMP preempt mod_unload aarch64"
        assert ".BTF" in run("readelf", "-S", str(built))
        checks.append(f"{name}: exact built bytes in initramfs, matching vermagic, BTF present")
    modules = (unpacked / "config").read_text()
    assert "tps6598x_core" in modules and "tps6598x" in modules
    checks.append("patched module pair explicitly included in early boot configuration")
    assert (unpacked / "hooks/asahi").read_bytes() == Path("/usr/lib/initcpio/hooks/asahi").read_bytes()
    assert (unpacked / "usr/share/asahi-scripts/functions.sh").is_file()
    assert (unpacked / "usr/lib/modules" / KERNEL / "kernel/drivers/gpu/drm/apple/appledrm.ko").is_file()
    assert "CONFIG_DRM_ASAHI=y" in (ROOT / "snapshots/running-kernel.config").read_text()
    checks.append("existing Asahi firmware hook and display module preserved; GPU remains in stock kernel")
    stock_dtb = Path(f"/usr/lib/modules/{KERNEL}/dtbs/t8103-j313.dtb")
    assert stock_dtb.read_bytes() == (ROOT / "artifacts/dtb/stock-j313-rebuilt.dtb").read_bytes()
    checks.append("stock DTB reproduced byte-for-byte from exact release source")
    spec = importlib.util.spec_from_file_location("bundle", ROOT / "scripts/stage-boot-bundle.py")
    bundle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bundle)
    new = bundle.properties((ROOT / "artifacts/dtb/t8103-j313.dtb").read_bytes())
    assert new[("/soc/dcp@271c00000", "status")] == b"okay\0"
    for malformed in (b"", b"\0" * 40, stock_dtb.read_bytes()[:-1]):
        try:
            bundle.properties(malformed)
        except ValueError:
            pass
        else:
            raise AssertionError("FDT validator accepted truncated/invalid input")
    checks.append("FDT parser rejects truncated/invalid headers")
    assert sha(Path("/boot/efi/m1n1/boot.bin")) == sha(ROOT / "snapshots/m1n1-boot.bin")
    assert sha(Path("/boot/vmlinuz-linux-asahi")) == "e339c992eef9bb879680513efee54aec68b39f14cba78f96b6db3a5c1d68533c"
    for name in ("tps6598x-core", "tps6598x"):
        stock = Path(f"/usr/lib/modules/{KERNEL}/kernel/drivers/usb/typec/tipd/{name}.ko")
        assert sha(stock) != sha(ROOT / f"artifacts/tipd/{name}.ko")
    checks.append("active m1n1 and kernel unchanged; installed modules remain distinct from test modules")
    report = {
        "checks": checks,
        "initramfs_sha256": sha(ROOT / "artifacts/initramfs-display-test.img"),
        "module_build": "passed with pahole 1.32 versus stock 1.31 metadata-version warning",
        "boot_tested": False,
        "display_output_verified": False,
        "limitations": ["No runtime module-load test", "No monitor connected during build", "Shared m1n1 DTB change requires attended boot and recovery preparation"],
    }
    (ROOT / "reports/verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
