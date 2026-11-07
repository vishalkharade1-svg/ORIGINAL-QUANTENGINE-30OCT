import json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'scripts/audit_phase60_9l_admission_readiness.py'
class TestPhase60(unittest.TestCase):
    def test_missing_genuine_report_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'r.json'; missing=Path(td)/'missing.json'
            subprocess.run([sys.executable,str(SCRIPT),'--report',str(missing),'--output',str(out)],cwd=ROOT,check=True)
            p=json.loads(out.read_text()); self.assertEqual(p['status'],'MISSING_GENUINE_9L_REPORT'); self.assertFalse(p['preregistration_created']); self.assertFalse(p['production_ready'])
    def test_identical_missing_runs_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/'a.json'; b=Path(td)/'b.json'; missing=Path(td)/'missing.json'
            for out in (a,b): subprocess.run([sys.executable,str(SCRIPT),'--report',str(missing),'--output',str(out)],cwd=ROOT,check=True)
            self.assertEqual(a.read_bytes(),b.read_bytes())
if __name__=='__main__': unittest.main()
