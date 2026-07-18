from pathlib import Path

import pytest

from repostyle.rules import RS_RANGE_LEN_REINDEX, check_range_len_reindex


class TestCheckRangeLenReindex:
    @pytest.mark.parametrize(
        "source",
        [
            pytest.param(
                "for i in range(len(rows)):\n    process(rows[i])\n",
                id="plain-reindex",
            ),
            pytest.param(
                "for i in range(len(rows)):\n    a = rows[i]\n    b = rows[i]\n",
                id="reindexed-twice",
            ),
            pytest.param(
                "for i in range(len(self.rows)):\n    process(self.rows[i])\n",
                id="attribute-sequence",
            ),
            pytest.param(
                "async def f():\n"
                "    async for i in range(len(rows)):\n"
                "        process(rows[i])\n",
                id="async-for",
            ),
            pytest.param(
                "for j in range(len(items)):\n"
                "    for i in range(len(rows)):\n"
                "        process(rows[i])\n",
                id="nested-inner",
            ),
        ],
    )
    def test_ReindexLoop_FlagsViolation(self, source: str) -> None:
        violations = list(check_range_len_reindex(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_RANGE_LEN_REINDEX

    def test_ReindexLoop_NamesTheSequence(self) -> None:
        source = "for i in range(len(rows)):\n    process(rows[i])\n"
        violations = list(check_range_len_reindex(Path("src/x.py"), source))
        assert "`rows`" in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            pytest.param(
                "for i in range(len(rows)):\n    process(i)\n",
                id="index-passed-to-call",
            ),
            pytest.param(
                "for i in range(len(rows)):\n    process(rows[i + 1])\n",
                id="index-in-arithmetic",
            ),
            pytest.param(
                "for i in range(len(rows)):\n    process(rows[i], cols[i])\n",
                id="indexes-a-second-sequence",
            ),
            pytest.param(
                "for i in range(len(rows)):\n    process(rows[i], i)\n",
                id="index-also-used-bare",
            ),
            pytest.param(
                "for i in range(len(rows)):\n    pass\n",
                id="index-unused",
            ),
            pytest.param(
                "for i in range(len(rows) - 1):\n    process(rows[i])\n",
                id="range-not-bare-len",
            ),
            pytest.param(
                "for i in range(0, len(rows)):\n    process(rows[i])\n",
                id="range-two-args",
            ),
            pytest.param(
                "for row in rows:\n    process(row)\n",
                id="already-direct",
            ),
            pytest.param(
                "for i, row in enumerate(rows):\n    process(rows[i])\n",
                id="tuple-target",
            ),
        ],
    )
    def test_LoopNeedingIndex_NoViolation(self, source: str) -> None:
        assert list(check_range_len_reindex(Path("src/x.py"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        source = "for i in range(len(rows)):\n    process(rows[i])\n"
        assert list(check_range_len_reindex(Path("README.md"), source)) == []
