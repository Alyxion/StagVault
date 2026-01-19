"""Tests for search prefix coverage.

Ensures all expected 2-letter alphabet combinations have prefix files.
"""

from __future__ import annotations

import json
import string
from pathlib import Path

import pytest


# These combinations have no items in the current dataset
# (verified by checking the actual index - these truly have no matches)
EMPTY_COMBINATIONS = {
    'bg', 'bk', 'bq', 'bv', 'bx', 'bz',
    'cb', 'cf', 'cg', 'cj',
    'dq', 'dx', 'dz',
    'fb', 'fd', 'fh', 'fj', 'fk', 'fn', 'fp', 'fq', 'fv', 'fw', 'fx', 'fz',
    'gc', 'gf', 'gj', 'gk', 'gq', 'gv', 'gw', 'gx', 'gz',
    'hc', 'hg', 'hh', 'hk', 'hm', 'hv', 'hx', 'hz',
    'jb', 'jc', 'jd', 'jf', 'jg', 'jh', 'jj', 'jk', 'jl', 'jm', 'jn', 'jq', 'jr', 'jt', 'jv', 'jw', 'jx', 'jy', 'jz',
    'kc', 'kj', 'kv', 'kx',
    'lj', 'ln', 'lq', 'lx', 'lz',
    'mg', 'mh', 'mj', 'mk', 'mq', 'mt', 'mv', 'mz',
    'oq',
    'pj', 'pq', 'pv', 'px', 'pz',
    'qb', 'qc', 'qd', 'qe', 'qf', 'qg', 'qh', 'qi', 'qj', 'qk', 'qm', 'qn', 'qo', 'qs', 'qt', 'qv', 'qw', 'qx', 'qy', 'qz',
    'rx',
    'sj', 'sz',
    'tk', 'tq',
    'vc', 'vf', 'vj', 'vm', 'vq', 'vt', 'vv', 'vw', 'vx', 'vz',
    'wg', 'wj', 'wk', 'wq', 'wu', 'wv', 'wx', 'wy', 'wz',
    'xf', 'xg', 'xj', 'xk', 'xq', 'xs', 'xu', 'xv', 'xw', 'xz',
    'yj', 'yk', 'yq', 'yx', 'yy',
    'zc', 'zd', 'zf', 'zg', 'zj', 'zk', 'zn', 'zp', 'zq', 'zr', 'zv', 'zx',
}


class TestPrefixCoverage:
    """Tests for search prefix file coverage."""

    @pytest.fixture
    def static_index_dir(self) -> Path:
        """Return the static index directory."""
        return Path("/projects/StagVault/static_site/index")

    @pytest.fixture
    def manifest(self, static_index_dir: Path) -> list[dict]:
        """Load the search manifest."""
        manifest_path = static_index_dir / "index" / "search" / "_manifest.json"
        if not manifest_path.exists():
            pytest.skip("Static index not built")
        with open(manifest_path) as f:
            return json.load(f)

    @pytest.fixture
    def existing_prefixes(self, manifest: list[dict]) -> set[str]:
        """Get set of existing prefixes from manifest."""
        return {entry["prefix"] for entry in manifest}

    def test_all_expected_alpha_combinations_exist(self, existing_prefixes: set[str]) -> None:
        """Test that all expected 2-letter combinations have prefix files.

        All 676 possible 2-letter combinations (aa-zz) should exist,
        EXCEPT for the known empty combinations that have no matching items.
        """
        # Generate all 2-letter combinations
        all_combos = set()
        for a in string.ascii_lowercase:
            for b in string.ascii_lowercase:
                all_combos.add(a + b)

        # Expected combinations = all minus known empty ones
        expected = all_combos - EMPTY_COMBINATIONS

        # Check that all expected combinations exist
        missing = expected - existing_prefixes
        assert len(missing) == 0, \
            f"Missing prefix files for: {sorted(missing)}"

    def test_common_prefixes_exist(self, existing_prefixes: set[str]) -> None:
        """Test that commonly searched prefixes have files.

        These are prefixes that users will definitely search for.
        """
        common_prefixes = [
            # Common word starts
            'ar', 'er', 'in', 'on', 'an', 'or', 'us', 'de', 'fr',
            # Icon-related
            'ic', 'bu', 'me', 'se', 'fi', 'fo', 'ho', 'he', 'st',
            # Actions
            'ad', 'ed', 'cl', 'op', 'sa', 'lo', 'do', 'up',
            # Objects
            'bo', 'ca', 'ch', 'co', 'li', 'ma', 'pa', 'pl', 'pr',
        ]

        missing = [p for p in common_prefixes if p not in existing_prefixes]
        assert len(missing) == 0, \
            f"Common prefixes missing: {missing}"

    def test_prefix_files_not_empty(self, static_index_dir: Path, manifest: list[dict]) -> None:
        """Test that prefix files have at least one item."""
        search_dir = static_index_dir / "index" / "search"

        empty_files = []
        for entry in manifest[:50]:  # Check first 50 to keep test fast
            prefix = entry["prefix"]
            prefix_file = search_dir / f"{prefix}.json"
            if prefix_file.exists():
                with open(prefix_file) as f:
                    items = json.load(f)
                if len(items) == 0:
                    empty_files.append(prefix)

        assert len(empty_files) == 0, \
            f"Empty prefix files found: {empty_files}"

    def test_er_prefix_has_items(self, static_index_dir: Path) -> None:
        """Test that 'er' prefix has items (regression test).

        The 'er' prefix was previously skipped as 'too common'.
        This test ensures it's now included.
        """
        er_file = static_index_dir / "index" / "search" / "er.json"
        assert er_file.exists(), "'er' prefix file should exist"

        with open(er_file) as f:
            items = json.load(f)

        # Should have many items (user, eraser, filter, etc.)
        assert len(items) >= 100, \
            f"'er' prefix should have 100+ items, got {len(items)}"

        # Verify some expected items
        names = [item.get("n", "").lower() for item in items]
        assert any("user" in n for n in names), "Should contain 'user' items"
        assert any("filter" in n for n in names), "Should contain 'filter' items"

    def test_us_prefix_has_flag(self, static_index_dir: Path) -> None:
        """Test that 'us' prefix includes US flag."""
        us_file = static_index_dir / "index" / "search" / "us.json"
        assert us_file.exists(), "'us' prefix file should exist"

        with open(us_file) as f:
            items = json.load(f)

        # Find US flag
        us_flags = [
            item for item in items
            if "flag" in item.get("n", "").lower()
            and "united states" in item.get("n", "").lower()
        ]

        assert len(us_flags) >= 1, "Should find US flag in 'us' prefix"

    def test_de_prefix_has_flag(self, static_index_dir: Path) -> None:
        """Test that 'de' prefix includes German flag."""
        de_file = static_index_dir / "index" / "search" / "de.json"
        assert de_file.exists(), "'de' prefix file should exist"

        with open(de_file) as f:
            items = json.load(f)

        # Find German flag
        de_flags = [
            item for item in items
            if "flag" in item.get("n", "").lower()
            and "germany" in item.get("n", "").lower()
        ]

        assert len(de_flags) >= 1, "Should find German flag in 'de' prefix"

    @pytest.mark.parametrize("prefix", [
        'aa', 'ab', 'ac', 'ad', 'ae', 'af', 'ag', 'ah', 'ai', 'aj', 'ak', 'al', 'am', 'an', 'ao', 'ap', 'aq', 'ar', 'as', 'at', 'au', 'av', 'aw', 'ax', 'ay', 'az',
        'ba', 'bb', 'bc', 'bd', 'be', 'bf', 'bi', 'bl', 'bo', 'br', 'bs', 'bt', 'bu', 'bw', 'by',
        'ca', 'cc', 'cd', 'ce', 'ch', 'ci', 'ck', 'cl', 'cm', 'cn', 'co', 'cp', 'cq', 'cr', 'cs', 'ct', 'cu', 'cv', 'cw', 'cx', 'cy', 'cz',
        'da', 'db', 'dc', 'dd', 'de', 'df', 'dg', 'dh', 'di', 'dj', 'dk', 'dl', 'dm', 'dn', 'do', 'dp', 'dr', 'ds', 'dt', 'du', 'dv', 'dw', 'dy',
        'ea', 'eb', 'ec', 'ed', 'ee', 'ef', 'eg', 'eh', 'ei', 'ej', 'ek', 'el', 'em', 'en', 'eo', 'ep', 'eq', 'er', 'es', 'et', 'eu', 'ev', 'ew', 'ex', 'ey', 'ez',
        'fa', 'fc', 'fe', 'ff', 'fi', 'fl', 'fm', 'fo', 'fr', 'fs', 'ft', 'fu', 'fy',
        'ga', 'gb', 'gd', 'ge', 'gh', 'gi', 'gl', 'gm', 'gn', 'go', 'gp', 'gr', 'gs', 'gt', 'gu', 'gy',
        'ha', 'hb', 'hd', 'he', 'hf', 'hi', 'hj', 'hl', 'hn', 'ho', 'hp', 'hq', 'hr', 'hs', 'ht', 'hu', 'hw', 'hy',
        'ia', 'ib', 'ic', 'id', 'ie', 'if', 'ig', 'ih', 'ii', 'ij', 'ik', 'il', 'im', 'in', 'io', 'ip', 'iq', 'ir', 'is', 'it', 'iu', 'iv', 'iw', 'ix', 'iy', 'iz',
        'ja', 'je', 'ji', 'jo', 'jp', 'js', 'ju',
        'ka', 'kb', 'kd', 'ke', 'kf', 'kg', 'kh', 'ki', 'kk', 'kl', 'km', 'kn', 'ko', 'kp', 'kq', 'kr', 'ks', 'kt', 'ku', 'kw', 'ky', 'kz',
        'la', 'lb', 'lc', 'ld', 'le', 'lf', 'lg', 'lh', 'li', 'lk', 'll', 'lm', 'lo', 'lp', 'lr', 'ls', 'lt', 'lu', 'lv', 'lw', 'ly',
        'ma', 'mb', 'mc', 'md', 'me', 'mf', 'mi', 'ml', 'mm', 'mn', 'mo', 'mp', 'mr', 'ms', 'mu', 'mw', 'mx', 'my',
        'na', 'nb', 'nc', 'nd', 'ne', 'nf', 'ng', 'nh', 'ni', 'nj', 'nk', 'nl', 'nm', 'nn', 'no', 'np', 'nq', 'nr', 'ns', 'nt', 'nu', 'nv', 'nw', 'nx', 'ny', 'nz',
        'oa', 'ob', 'oc', 'od', 'oe', 'of', 'og', 'oh', 'oi', 'oj', 'ok', 'ol', 'om', 'on', 'oo', 'op', 'or', 'os', 'ot', 'ou', 'ov', 'ow', 'ox', 'oy', 'oz',
        'pa', 'pb', 'pc', 'pd', 'pe', 'pf', 'pg', 'ph', 'pi', 'pk', 'pl', 'pm', 'pn', 'po', 'pp', 'pr', 'ps', 'pt', 'pu', 'pw', 'py',
        'qa', 'ql', 'qp', 'qr', 'qu',
        'ra', 'rb', 'rc', 'rd', 're', 'rf', 'rg', 'rh', 'ri', 'rj', 'rk', 'rl', 'rm', 'rn', 'ro', 'rp', 'rq', 'rr', 'rs', 'rt', 'ru', 'rv', 'rw', 'ry', 'rz',
        'sa', 'sb', 'sc', 'sd', 'se', 'sf', 'sg', 'sh', 'si', 'sk', 'sl', 'sm', 'sn', 'so', 'sp', 'sq', 'sr', 'ss', 'st', 'su', 'sv', 'sw', 'sx', 'sy',
        'ta', 'tb', 'tc', 'td', 'te', 'tf', 'tg', 'th', 'ti', 'tj', 'tl', 'tm', 'tn', 'to', 'tp', 'tr', 'ts', 'tt', 'tu', 'tv', 'tw', 'tx', 'ty', 'tz',
        'ua', 'ub', 'uc', 'ud', 'ue', 'uf', 'ug', 'uh', 'ui', 'uj', 'uk', 'ul', 'um', 'un', 'uo', 'up', 'uq', 'ur', 'us', 'ut', 'uu', 'uv', 'uw', 'ux', 'uy', 'uz',
        'va', 'vb', 'vd', 've', 'vg', 'vh', 'vi', 'vk', 'vl', 'vn', 'vo', 'vp', 'vr', 'vs', 'vu', 'vy',
        'wa', 'wb', 'wc', 'wd', 'we', 'wf', 'wh', 'wi', 'wl', 'wm', 'wn', 'wo', 'wp', 'wr', 'ws', 'wt', 'ww',
        'xa', 'xb', 'xc', 'xd', 'xe', 'xh', 'xi', 'xl', 'xm', 'xn', 'xo', 'xp', 'xr', 'xt', 'xx', 'xy',
        'ya', 'yb', 'yc', 'yd', 'ye', 'yf', 'yg', 'yh', 'yi', 'yl', 'ym', 'yn', 'yo', 'yp', 'yr', 'ys', 'yt', 'yu', 'yw', 'yz',
        'za', 'zb', 'ze', 'zh', 'zi', 'zl', 'zm', 'zo', 'zs', 'zt', 'zu', 'zw', 'zy', 'zz',
    ])
    def test_prefix_file_exists(self, static_index_dir: Path, prefix: str) -> None:
        """Test that each expected prefix file exists and is valid JSON."""
        prefix_file = static_index_dir / "index" / "search" / f"{prefix}.json"
        assert prefix_file.exists(), f"Prefix file '{prefix}.json' should exist"

        # Verify it's valid JSON with items
        with open(prefix_file) as f:
            items = json.load(f)

        assert isinstance(items, list), f"'{prefix}.json' should contain a list"
        assert len(items) > 0, f"'{prefix}.json' should not be empty"
