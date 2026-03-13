"""
test_oss.py -- GitHub Radar OSS automated tests
Test layers:
  1. Syntax check: Can all .py files compile
  2. Import check: Can each script import gh_utils correctly
  3. Unit tests: Pure functions like parse_repo_input, print_json, is_ai_related
  4. Light API tests: check_rate_limit, one search, one repo view
  5. Integration tests: End-to-end run of each script (valid JSON output)
"""

import subprocess
import json
import sys
import os
import unittest
from unittest.mock import patch
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)


class T1_SyntaxCheck(unittest.TestCase):
    """All .py files should pass compile"""

    def _check_compile(self, filename):
        path = os.path.join(SCRIPT_DIR, filename)
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        try:
            compile(source, filename, "exec")
        except SyntaxError as e:
            self.fail(f"{filename} syntax error: {e}")

    def test_gh_utils(self):
        self._check_compile("gh_utils.py")

    def test_radar_pulse(self):
        self._check_compile("radar_pulse.py")

    def test_search_repos(self):
        self._check_compile("search_repos.py")

    def test_watch_signals(self):
        self._check_compile("watch_signals.py")

    def test_deep_link(self):
        self._check_compile("deep_link.py")

    def test_fetch_star_history(self):
        self._check_compile("fetch_star_history.py")

    def test_check_rate_limit(self):
        self._check_compile("check_rate_limit.py")

    def test_generate_report(self):
        self._check_compile("generate_report.py")


class T2_ImportCheck(unittest.TestCase):
    """Each script should import successfully"""

    def test_import_gh_utils(self):
        import gh_utils
        self.assertTrue(hasattr(gh_utils, "run_gh"))
        self.assertTrue(hasattr(gh_utils, "run_gh_search"))
        self.assertTrue(hasattr(gh_utils, "parse_repo_input"))
        self.assertTrue(hasattr(gh_utils, "print_json"))

    def test_import_radar_pulse(self):
        import radar_pulse
        self.assertTrue(hasattr(radar_pulse, "main"))
        self.assertTrue(hasattr(radar_pulse, "is_ai_related"))

    def test_import_search_repos(self):
        import search_repos
        self.assertTrue(hasattr(search_repos, "main"))
        self.assertTrue(hasattr(search_repos, "search"))

    def test_import_watch_signals(self):
        import watch_signals
        self.assertTrue(hasattr(watch_signals, "main"))
        self.assertTrue(hasattr(watch_signals, "collect_candidates"))

    def test_import_deep_link(self):
        import deep_link
        self.assertTrue(hasattr(deep_link, "main"))
        self.assertTrue(hasattr(deep_link, "get_base_info"))

    def test_import_fetch_star_history(self):
        import fetch_star_history
        self.assertTrue(hasattr(fetch_star_history, "main"))
        self.assertTrue(hasattr(fetch_star_history, "fetch_stargazers"))

    def test_import_generate_report(self):
        import generate_report
        self.assertTrue(hasattr(generate_report, "main"))
        self.assertTrue(hasattr(generate_report, "render_simple"))


class T3_UnitTests(unittest.TestCase):
    """Pure function unit tests (no API calls)"""

    def test_parse_repo_input_slash(self):
        from gh_utils import parse_repo_input
        owner, name = parse_repo_input("langchain-ai/langgraph")
        self.assertEqual(owner, "langchain-ai")
        self.assertEqual(name, "langgraph")

    def test_parse_repo_input_url(self):
        from gh_utils import parse_repo_input
        owner, name = parse_repo_input("https://github.com/anthropics/claude-code")
        self.assertEqual(owner, "anthropics")
        self.assertEqual(name, "claude-code")

    def test_parse_repo_input_url_trailing_slash(self):
        from gh_utils import parse_repo_input
        owner, name = parse_repo_input("https://github.com/facebook/react/")
        self.assertEqual(owner, "facebook")
        self.assertEqual(name, "react")

    def test_parse_repo_input_invalid(self):
        from gh_utils import parse_repo_input
        owner, name = parse_repo_input("justoneword")
        self.assertIsNone(owner)
        self.assertIsNone(name)

    def test_print_json_output(self):
        """print_json tested via subprocess (setup_utf8_stdout replaces sys.stdout)"""
        result = subprocess.run(
            [sys.executable, "-c",
             'import sys; sys.path.insert(0,r"' + SCRIPT_DIR + '"); '
             'from gh_utils import print_json; '
             'print_json({"key":"value","num":42,"cn":"中文"})'],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace"
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        data = json.loads(result.stdout)
        self.assertEqual(data["key"], "value")
        self.assertEqual(data["num"], 42)
        self.assertEqual(data["cn"], "中文")

    def test_is_ai_related_true(self):
        from radar_pulse import is_ai_related
        repo = {"name": "my-llm-agent", "description": "An AI agent framework"}
        self.assertTrue(is_ai_related(repo))

    def test_is_ai_related_false(self):
        from radar_pulse import is_ai_related
        repo = {"name": "react-ui-kit", "description": "A UI component library"}
        self.assertFalse(is_ai_related(repo))

    def test_render_simple_vars(self):
        from generate_report import render_simple
        template = "<h1>{{title}}</h1><p>{{count}} items</p>"
        data = {"title": "Test Report", "count": 5}
        result = render_simple(template, data)
        self.assertIn("Test Report", result)
        self.assertIn("5 items", result)

    def test_render_simple_each(self):
        from generate_report import render_simple
        template = "<ul>{{#each items}}<li>{{name}} - {{stars}}</li>{{/each}}</ul>"
        data = {"items": [{"name": "repo1", "stars": 100}, {"name": "repo2", "stars": 200}]}
        result = render_simple(template, data)
        self.assertIn("repo1 - 100", result)
        self.assertIn("repo2 - 200", result)

    def test_analyze_issues_empty(self):
        """deep_link.analyze_issues should handle empty input"""
        from deep_link import analyze_issues
        with patch("deep_link.run_gh", return_value=None):
            result = analyze_issues("fake/repo")
            self.assertEqual(result["total_sampled"], 0)

    def test_enrich_candidates(self):
        """watch_signals.enrich_candidates computes rough velocity"""
        from watch_signals import enrich_candidates
        today = datetime.now().strftime("%Y-%m-%d")
        repos = {
            "test/repo": {
                "stargazersCount": 100,
                "forksCount": 10,
                "createdAt": today,
                "description": "test",
                "language": "Python",
                "url": "https://github.com/test/repo"
            }
        }
        candidates = enrich_candidates(repos)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["full_name"], "test/repo")
        self.assertEqual(candidates[0]["stars"], 100)
        self.assertGreater(candidates[0]["rough_velocity"], 0)

    def test_search_repos_search_function(self):
        """search_repos.search runs correctly in a mock environment"""
        from search_repos import search
        with patch("search_repos.run_gh_search", return_value=[
            {
                "owner": {"login": "test"},
                "name": "repo1",
                "description": "an llm tool",
                "stargazersCount": 500,
                "forksCount": 50,
                "updatedAt": "2026-03-01T00:00:00Z",
                "createdAt": "2026-01-01T00:00:00Z",
                "language": "Python",
                "url": "https://github.com/test/repo1",
                "isArchived": False,
                "license": None
            }
        ]):
            result = search(["test query"], min_stars=100, min_recall=1)
            self.assertGreater(result["total_found"], 0)
            self.assertEqual(result["repos"][0]["full_name"], "test/repo1")


class T4_LightAPITests(unittest.TestCase):
    """Light API tests -- actual gh CLI calls (requires network and authentication)"""

    @classmethod
    def setUpClass(cls):
        """Check if gh is available"""
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True, text=True, timeout=10
            )
            cls.gh_available = result.returncode == 0
        except Exception:
            cls.gh_available = False

        if not cls.gh_available:
            return

        # Check rate limit
        try:
            result = subprocess.run(
                ["gh", "api", "rate_limit", "--jq", ".rate.remaining"],
                capture_output=True, text=True, timeout=10
            )
            cls.rate_remaining = int(result.stdout.strip()) if result.returncode == 0 else 0
        except Exception:
            cls.rate_remaining = 0

    def setUp(self):
        if not self.gh_available:
            self.skipTest("gh CLI not authenticated")
        if self.rate_remaining < 50:
            self.skipTest(f"Rate limit too low: {self.rate_remaining}")

    def test_check_rate_limit_script(self):
        """check_rate_limit.py outputs valid JSON"""
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, "check_rate_limit.py")],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace"
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        data = json.loads(result.stdout)
        self.assertIn("remaining", data)
        self.assertIn("mode", data)
        self.assertIn(data["mode"], ["full", "degraded", "minimal"])

    def test_run_gh_basic(self):
        """gh_utils.run_gh returns data correctly"""
        from gh_utils import run_gh
        result = run_gh(["api", "repos/cli/cli", "--jq", ".name"])
        self.assertIsNotNone(result)
        self.assertEqual(result, "cli")

    def test_run_gh_search_basic(self):
        """gh_utils.run_gh_search returns a list"""
        from gh_utils import run_gh_search
        results = run_gh_search(["cli", "--sort", "stars", "--limit", "3"])
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        self.assertIn("owner", results[0])
        self.assertIn("stargazersCount", results[0])


class T5_IntegrationTests(unittest.TestCase):
    """End-to-end integration tests -- each script outputs valid JSON"""

    @classmethod
    def setUpClass(cls):
        try:
            result = subprocess.run(
                ["gh", "api", "rate_limit", "--jq", ".rate.remaining"],
                capture_output=True, text=True, timeout=10
            )
            cls.rate_remaining = int(result.stdout.strip()) if result.returncode == 0 else 0
        except Exception:
            cls.rate_remaining = 0

    def _run_script(self, script_name, args=None, timeout=60):
        cmd = [sys.executable, os.path.join(SCRIPT_DIR, script_name)]
        if args:
            cmd.extend(args)
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace"
        )
        return result

    def setUp(self):
        if self.rate_remaining < 100:
            self.skipTest(f"Rate limit too low for integration tests: {self.rate_remaining}")

    def test_radar_pulse_output_json(self):
        """radar_pulse.py --days 3 outputs valid JSON"""
        result = self._run_script("radar_pulse.py", ["--days", "3"])
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        data = json.loads(result.stdout)
        self.assertIn("scan_date", data)
        self.assertIn("candidates", data)
        self.assertIsInstance(data["candidates"], list)

    def test_search_repos_output_json(self):
        """search_repos.py 'llm agent' outputs valid JSON"""
        result = self._run_script("search_repos.py", ["llm agent", "--min-recall", "5"])
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        data = json.loads(result.stdout)
        self.assertIn("keywords", data)
        self.assertIn("repos", data)
        self.assertIsInstance(data["repos"], list)

    def test_watch_signals_output_json(self):
        """watch_signals.py outputs valid JSON"""
        result = self._run_script("watch_signals.py", timeout=120)
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        data = json.loads(result.stdout)
        self.assertIn("candidates", data)
        self.assertIn("scan_date", data)

    def test_deep_link_output_json(self):
        """deep_link.py cli/cli outputs valid JSON (small repo to save API calls)"""
        result = self._run_script("deep_link.py", ["cli/cli"], timeout=180)
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        data = json.loads(result.stdout)
        self.assertIn("repo", data)
        self.assertIn("base", data)
        self.assertIn("adoption_signals", data)

    def test_fetch_star_history_output_json(self):
        """fetch_star_history.py cli/cli outputs valid JSON"""
        result = self._run_script("fetch_star_history.py", ["cli/cli"], timeout=120)
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        data = json.loads(result.stdout)
        self.assertIn("repo", data)
        self.assertIn("total_stars", data)


class T6_ReportRenderTests(unittest.TestCase):
    """generate_report.py template rendering tests -- full pipeline for all 4 modes"""

    TEMPLATE_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "en", "templates")

    def _make_analysis(self, mode):
        """Construct minimal renderable analysis JSON for each mode"""
        if mode == "radar-pulse":
            return {
                "date": "2026-01-01", "total_scanned": 50, "picks_count": 2,
                "headline": "Test headline for radar pulse",
                "picks": [{
                    "full_name": "test/repo1", "url": "https://github.com/test/repo1",
                    "layer": "L2", "layer_class": "l2", "description": "Test repo",
                    "stars_fmt": "1,000", "growth_30d_fmt": "+500", "growth_7d_fmt": "+100",
                    "precision": "exact", "language": "Python", "created": "2026-01-01",
                    "signals": ["hot"], "signals_html": "<span class=\"signal-tag\">hot</span>",
                    "why": "Test reason", "paradigm": "Test paradigm"
                }],
                "trends": [{"title": "Test trend", "narrative": "Test narrative", "repos_html": ""}],
                "scan_overview": [{"full_name": "test/repo2", "url": "#", "layer": "L3",
                                   "layer_class": "l3", "stars_fmt": "500", "one_liner": "Test"}],
                "filtered_groups": [{"label": "L5", "count": 3, "reason": "wrappers", "items": "a, b, c"}]
            }
        elif mode == "direction-search":
            return {
                "topic": "test topic", "date": "2026-01-01",
                "meta": "10 repos scanned", "headline": "Test headline for direction search",
                "legend_html": "<span class=\"badge badge-l2\">L2</span>",
                "keywords_count": 2, "keywords_html": "<code>kw1</code> <code>kw2</code>",
                "picks": [{
                    "full_name": "test/repo1", "url": "#",
                    "badge_html": "<span class=\"badge badge-l2\">L2</span>",
                    "signals_html": "", "description": "Test",
                    "metrics_html": "<tr><td>Stars</td><td>1000</td></tr>",
                    "why": "Test", "paradigm": "Test"
                }],
                "landscape_html": "<p>Test landscape</p>",
                "paradigm_content": "<strong>Test</strong>",
                "suggestions": [{"name": "test/repo1", "url": "#", "suggestion": "Deep link it"}],
                "filtered_summary": "5", "filtered_html": "<p>filtered</p>",
                "footer_stats": "2026-01-01 · 10 repos"
            }
        elif mode == "signal-watch":
            return {
                "date": "2026-01-01", "total_candidates": 30, "verified_count": 5,
                "scan_mode": "global", "headline": "Test headline for signal watch",
                "focus_items": [{"title": "Focus 1", "detail": "Detail 1"}],
                "picks": [{
                    "full_name": "test/repo1", "url": "#", "layer": "L2", "layer_class": "l2",
                    "stars_fmt": "1,000", "created_short": "01-01",
                    "pattern_class": "sustained", "pattern_label": "sustained", "one_liner": "Test"
                }],
                "pick_details": [{
                    "full_name": "test/repo1", "url": "#", "layer": "L2", "layer_class": "l2",
                    "pattern_class": "sustained", "pattern_label": "sustained",
                    "description": "Test", "language": "Python",
                    "stars_fmt": "1,000", "forks_fmt": "100", "created_short": "01-01",
                    "growth_7d_fmt": "+100", "avg_daily": "14/d", "consecutive_label": "7 days",
                    "spark_points": "0,30 100,20 200,10", "spark_markers": "", "spark_label": "up",
                    "pm_insight": "Test insight"
                }],
                "seed_count": 76,
                "dev_activities": [{"github": "test-dev", "note": "tester", "activity_html": "new repo"}],
                "other_signals": [{"full_name": "test/repo2", "url": "#", "stars_fmt": "500",
                                   "created_short": "01-01", "velocity": "50/d", "description_short": "Test"}],
                "filtered_summary": "10 filtered",
                "filtered_groups": [{"label": "L5", "count": 10, "reason": "wrappers", "items": "a,b,c"}],
                "cost_detail": "~$0.02"
            }
        elif mode == "deep-link":
            return {
                "owner": "test", "repo_name": "repo1", "date": "2026-01-01",
                "oneliner": "Test headline for deep link analysis",
                "stars": "1,000", "forks": "100",
                "forks_comment": "Normal", "growth_7d": "+50", "growth_comment": "Steady",
                "peak_day": "01-01 (20)", "peak_comment": "", "growth_pattern": "Sustained",
                "growth_pattern_comment": "", "commits_90d": "100", "commits_7d": "10",
                "commits_7d_avg": "1.4", "commits_7d_comment": "", "commits_30d": "40",
                "commits_30d_avg": "1.3", "commits_30d_comment": "",
                "language": "Python", "language_comment": "", "license": "MIT",
                "created_at": "2025-01-01", "age_comment": "1 year",
                "y_25pct": "5", "y_50pct": "10", "y_75pct": "15", "y_max": "20",
                "area_path": "M50,160 L300,100 L540,160Z",
                "line_points": "50,140 300,100 540,120",
                "data_circles": "", "peak_annotation": "", "x_labels": "",
                "star_chart_summary": "Steady growth",
                "layer_badge_class": "layer-badge-l3", "layer_label": "L3",
                "layer_description": "Test", "layer_reasons": "<li>Reason</li>",
                "layer_alternative": "L2", "layer_alternative_reason": "Because",
                "fork_ratio": "10.0", "fork_ratio_comment": "",
                "watch_ratio": "1.0", "watchers": "10", "watch_ratio_comment": "",
                "issue_rate": "0.5", "issue_rate_comment": "",
                "zero_reply_pct": "20", "zero_reply_comment": "",
                "avg_comments": "2.0", "avg_comments_comment": "",
                "high_star_forks_count": "3", "high_star_forks_comment": "",
                "adoption_pm_title": "Adoption", "adoption_pm_bullets": "<li>Point</li>",
                "contributor_rows": "<tr><td>1</td><td>dev1</td><td>100</td><td>core</td></tr>",
                "contributor_pm_bullets": "<li>Bus factor = 1</li>",
                "release_tags": "<span class=\"rel\">v1.0</span>",
                "release_analysis": "Monthly releases",
                "issue_rows": "<tr><td>Bug</td><td>10</td><td>50%</td><td>Normal</td></tr>",
                "issue_sample_note": "Based on 20 issues",
                "innovation_intro": "Test innovation",
                "innovation_diagram": "A -> B -> C",
                "innovation_pm_title": "Innovation", "innovation_pm_bullets": "<li>Key</li>",
                "ecosystem_diagram": "Core -> Plugin", "ecosystem_pm_bullets": "<li>Eco</li>",
                "paradigm_headline": "Test paradigm", "paradigm_body": "Body",
                "paradigm_threatened": "<li>X</li>", "paradigm_not_threatened": "<li>Y</li>",
                "maturity": "Growth", "credibility": "High", "growth_nature": "Organic",
                "pm_value": "High", "risks": "None", "recommendation": "Watch",
                "competitor_count": 3, "competitor_note": "Topic search",
                "competitor_rows": "<tr><td>comp/1</td><td>5k</td><td>Yes</td></tr>",
                "cost": "0.05"
            }
        return {}

    def _render_mode(self, mode):
        """Render the specified mode and return the HTML string"""
        from generate_report import load_template, render_simple, preprocess_data
        data = self._make_analysis(mode)
        data = preprocess_data(data)
        template = load_template(mode, "en")
        return render_simple(template, data)

    def test_radar_pulse_render(self):
        """radar-pulse template renders successfully with key content"""
        html = self._render_mode("radar-pulse")
        self.assertIn("Radar Pulse", html)
        self.assertIn("Test headline for radar pulse", html)
        self.assertIn("test/repo1", html)
        self.assertIn("Featured Picks", html)
        self.assertNotIn("{{", html, "Template variables not replaced")

    def test_direction_search_render(self):
        """direction-search template renders successfully with key content"""
        html = self._render_mode("direction-search")
        self.assertIn("Direction Search", html)
        self.assertIn("test topic", html)
        self.assertIn("Test headline for direction search", html)
        self.assertIn("Notable Picks", html)
        self.assertNotIn("{{", html, "Template variables not replaced")

    def test_signal_watch_render(self):
        """signal-watch template renders successfully with key content"""
        html = self._render_mode("signal-watch")
        self.assertIn("Signal Watch", html)
        self.assertIn("Test headline for signal watch", html)
        self.assertIn("PM Focus", html)
        self.assertIn("Focus 1", html)
        self.assertNotIn("{{", html, "Template variables not replaced")

    def test_deep_link_render(self):
        """deep-link template renders successfully with key content"""
        html = self._render_mode("deep-link")
        self.assertIn("Deep Link", html)
        self.assertIn("Test headline for deep link analysis", html)
        self.assertIn("Profile", html)
        self.assertIn("Layer Classification", html)
        self.assertIn("PM Summary", html)
        # deep-link template has {{ placeholders in HTML comments (Agent instructions), only check non-comment parts
        import re
        html_no_comments = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
        self.assertNotIn("{{", html_no_comments, "Template variables not replaced")

    def test_all_templates_produce_valid_html(self):
        """All templates should output starting with <!DOCTYPE html>"""
        for mode in ["radar-pulse", "direction-search", "signal-watch", "deep-link"]:
            html = self._render_mode(mode)
            self.assertTrue(html.strip().startswith("<!DOCTYPE html>"),
                            f"{mode} template output does not start with DOCTYPE")
            self.assertIn("</html>", html, f"{mode} template missing closing </html>")

    def test_generate_report_e2e(self):
        """generate_report.py end-to-end: JSON file -> HTML file"""
        import tempfile
        data = self._make_analysis("radar-pulse")
        data = __import__("generate_report").preprocess_data(data)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False,
                                         encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            json_path = f.name

        out_prefix = os.path.join(tempfile.gettempdir(), "test_report_e2e")
        try:
            result = subprocess.run(
                [sys.executable, os.path.join(SCRIPT_DIR, "generate_report.py"),
                 json_path, "--mode", "radar-pulse", "--output", out_prefix],
                capture_output=True, text=True, timeout=15,
                encoding="utf-8", errors="replace"
            )
            self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
            output = json.loads(result.stdout)
            self.assertIn("html_path", output)
            self.assertGreater(output["html_chars"], 0)

            # Verify HTML file exists and is readable
            html_path = out_prefix + ".html"
            self.assertTrue(os.path.exists(html_path), f"HTML file not found: {html_path}")
            with open(html_path, encoding="utf-8") as f:
                html = f.read()
            self.assertIn("Radar Pulse", html)
        finally:
            for ext in [".json", ".html", ".md"]:
                path = (json_path if ext == ".json" else out_prefix + ext)
                if os.path.exists(path):
                    os.remove(path)


if __name__ == "__main__":
    # Run test layers sequentially; earlier layer failures don't affect later layers
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Load in order
    for cls in [T1_SyntaxCheck, T2_ImportCheck, T3_UnitTests,
                T4_LightAPITests, T5_IntegrationTests, T6_ReportRenderTests]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Output summary
    print("\n" + "=" * 60)
    total = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    skipped = len(result.skipped)
    passed = total - failures - errors - skipped
    print(f"TOTAL: {total} | PASS: {passed} | FAIL: {failures} | ERROR: {errors} | SKIP: {skipped}")
    print("=" * 60)
