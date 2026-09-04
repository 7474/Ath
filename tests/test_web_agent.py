#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class WebAgentHarnessTest(unittest.TestCase):
    def test_node_vector_agent_harness(self):
        from baronh.ingest import write_lexicon
        from baronh.lexicon import load_lexicon
        from baronh.vectordb import embed_text, write_index

        dest = Path(tempfile.mkdtemp(prefix="ath-vectors-"))
        lex = load_lexicon()
        write_lexicon(lex, dest / "lexicon.json")
        write_index(lex, dest)
        env = os.environ.copy()
        env["VECTORS_DIR"] = str(dest)
        env["EMBED_LIGHT_0"] = repr(float(embed_text("光")[0]))
        completed = subprocess.run(
            ["node", str(ROOT / "tests" / "test_web_agent.js")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("light=sairiac", completed.stdout)
        self.assertIn("gereulacr sairiac mire.", completed.stdout)
        self.assertIn("prebuilt=", completed.stdout)


if __name__ == "__main__":
    unittest.main()
