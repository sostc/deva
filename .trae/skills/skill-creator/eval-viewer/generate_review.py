#!/usr/bin/env python3
"""Generate an HTML review viewer for skill test results."""

import json
import argparse
from pathlib import Path
import webbrowser
import http.server
import socketserver
import threading
import time


def generate_html(workspace, skill_name, benchmark_path, previous_workspace=None):
    """Generate HTML content for the review viewer."""
    # Collect data
    evals = []
    for eval_dir in workspace.iterdir():
        if not eval_dir.is_dir() or not eval_dir.name.startswith("eval-"):
            continue

        eval_data = {
            "name": eval_dir.name,
            "prompt": "",
            "with_skill": None,
            "without_skill": None,
            "old_skill": None
        }

        # Read eval metadata
        meta_path = eval_dir / "eval_metadata.json"
        if meta_path.exists():
            with open(meta_path, "r") as f:
                meta = json.load(f)
                eval_data["prompt"] = meta.get("prompt", "")

        # Read with_skill output
        with_skill_dir = eval_dir / "with_skill" / "outputs"
        if with_skill_dir.exists():
            output_files = []
            for file in with_skill_dir.iterdir():
                if file.is_file():
                    try:
                        content = file.read_text(encoding="utf-8")
                        output_files.append({"name": file.name, "content": content})
                    except:
                        output_files.append({"name": file.name, "content": "[Binary file]"})
            eval_data["with_skill"] = output_files

        # Read without_skill output
        without_skill_dir = eval_dir / "without_skill" / "outputs"
        if without_skill_dir.exists():
            output_files = []
            for file in without_skill_dir.iterdir():
                if file.is_file():
                    try:
                        content = file.read_text(encoding="utf-8")
                        output_files.append({"name": file.name, "content": content})
                    except:
                        output_files.append({"name": file.name, "content": "[Binary file]"})
            eval_data["without_skill"] = output_files

        # Read old_skill output
        old_skill_dir = eval_dir / "old_skill" / "outputs"
        if old_skill_dir.exists():
            output_files = []
            for file in old_skill_dir.iterdir():
                if file.is_file():
                    try:
                        content = file.read_text(encoding="utf-8")
                        output_files.append({"name": file.name, "content": content})
                    except:
                        output_files.append({"name": file.name, "content": "[Binary file]"})
            eval_data["old_skill"] = output_files

        evals.append(eval_data)

    # Read benchmark data
    benchmark_data = {}
    if benchmark_path and benchmark_path.exists():
        with open(benchmark_path, "r") as f:
            benchmark_data = json.load(f)

    # Read previous feedback
    previous_feedback = {}
    if previous_workspace:
        feedback_path = previous_workspace / "feedback.json"
        if feedback_path.exists():
            with open(feedback_path, "r") as f:
                feedback = json.load(f)
                for review in feedback.get("reviews", []):
                    previous_feedback[review.get("run_id")] = review.get("feedback", "")

    # Generate HTML
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{skill_name} Review</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .tab {{ display: none; }}
        .tab.active {{ display: block; }}
        .nav {{ margin-bottom: 20px; }}
        .nav button {{ margin-right: 10px; padding: 10px; }}
        .eval {{ margin-bottom: 30px; padding: 20px; border: 1px solid #ddd; }}
        .output {{ margin-top: 10px; padding: 10px; background: #f5f5f5; }}
        .file {{ margin-top: 10px; }}
        .file-name {{ font-weight: bold; }}
        .file-content {{ white-space: pre-wrap; margin-top: 5px; }}
        textarea {{ width: 100%; height: 100px; margin-top: 10px; }}
        .feedback {{ margin-top: 10px; }}
        .previous-feedback {{ margin-top: 5px; padding: 5px; background: #e9e9e9; font-size: 12px; }}
    </style>
</head>
<body>
    <h1>{skill_name} Review</h1>
    
    <div class="nav">
        <button onclick="openTab('outputs')">Outputs</button>
        <button onclick="openTab('benchmark')">Benchmark</button>
    </div>

    <div id="outputs" class="tab active">
        {eval_sections}
        <button onclick="submitFeedback()">Submit All Reviews</button>
    </div>

    <div id="benchmark" class="tab">
        <h2>Benchmark Results</h2>
        {benchmark_section}
    </div>

    <script>
        const evals = {evals_json};
        const previousFeedback = {previous_feedback_json};

        function openTab(tabName) {
            const tabs = document.getElementsByClassName("tab");
            for (let i = 0; i < tabs.length; i++) {
                tabs[i].classList.remove("active");
            }
            document.getElementById(tabName).classList.add("active");
        }

        function submitFeedback() {
            const reviews = [];
            const textareas = document.querySelectorAll('textarea');
            textareas.forEach(textarea => {
                const runId = textarea.id;
                const feedback = textarea.value;
                reviews.push({{
                    run_id: runId,
                    feedback: feedback,
                    timestamp: new Date().toISOString()
                }});
            });

            const feedbackData = {{
                reviews: reviews,
                status: "complete"
            }};

            // Download feedback as JSON
            const dataStr = JSON.stringify(feedbackData, null, 2);
            const dataBlob = new Blob([dataStr], {{type: 'application/json'}});
            const url = URL.createObjectURL(dataBlob);
            const link = document.createElement('a');
            link.href = url;
            link.download = 'feedback.json';
            link.click();
        }
    </script>
</body>
</html>
"""

    # Generate eval sections
    eval_sections = []
    for i, eval_data in enumerate(evals):
        eval_section = f"""
        <div class="eval">
            <h2>Eval {i+1}: {eval_data['name']}</h2>
            <div><strong>Prompt:</strong> {eval_data['prompt']}</div>
        """

        # With skill output
        if eval_data['with_skill']:
            eval_section += f"""
            <div>
                <h3>With Skill</h3>
                <div class="output">
                    {''.join([f'<div class="file"><div class="file-name">{f["name"]}</div><div class="file-content">{f["content"]}</div></div>' for f in eval_data['with_skill']])}
                </div>
                <div class="feedback">
                    <label for="{eval_data['name']}-with_skill">Feedback:</label>
                    <textarea id="{eval_data['name']}-with_skill">{previous_feedback.get(f"{eval_data['name']}-with_skill", "")}</textarea>
                    {f'<div class="previous-feedback">Previous feedback: {previous_feedback.get(f"{eval_data['name']}-with_skill", "")}</div>' if previous_feedback.get(f"{eval_data['name']}-with_skill") else ''}
                </div>
            </div>
            """

        # Without skill output
        if eval_data['without_skill']:
            eval_section += f"""
            <div>
                <h3>Without Skill</h3>
                <div class="output">
                    {''.join([f'<div class="file"><div class="file-name">{f["name"]}</div><div class="file-content">{f["content"]}</div></div>' for f in eval_data['without_skill']])}
                </div>
                <div class="feedback">
                    <label for="{eval_data['name']}-without_skill">Feedback:</label>
                    <textarea id="{eval_data['name']}-without_skill">{previous_feedback.get(f"{eval_data['name']}-without_skill", "")}</textarea>
                    {f'<div class="previous-feedback">Previous feedback: {previous_feedback.get(f"{eval_data['name']}-without_skill", "")}</div>' if previous_feedback.get(f"{eval_data['name']}-without_skill") else ''}
                </div>
            </div>
            """

        # Old skill output
        if eval_data['old_skill']:
            eval_section += f"""
            <div>
                <h3>Old Skill</h3>
                <div class="output">
                    {''.join([f'<div class="file"><div class="file-name">{f["name"]}</div><div class="file-content">{f["content"]}</div></div>' for f in eval_data['old_skill']])}
                </div>
                <div class="feedback">
                    <label for="{eval_data['name']}-old_skill">Feedback:</label>
                    <textarea id="{eval_data['name']}-old_skill">{previous_feedback.get(f"{eval_data['name']}-old_skill", "")}</textarea>
                    {f'<div class="previous-feedback">Previous feedback: {previous_feedback.get(f"{eval_data['name']}-old_skill", "")}</div>' if previous_feedback.get(f"{eval_data['name']}-old_skill") else ''}
                </div>
            </div>
            """

        eval_section += "</div>"
        eval_sections.append(eval_section)

    # Generate benchmark section
    benchmark_section = ""
    if benchmark_data:
        benchmark_section = f"""
        <pre>{json.dumps(benchmark_data, indent=2)}</pre>
        """

    # Replace placeholders
    html = html.format(
        skill_name=skill_name,
        eval_sections='\n'.join(eval_sections),
        benchmark_section=benchmark_section,
        evals_json=json.dumps(evals),
        previous_feedback_json=json.dumps(previous_feedback)
    )

    return html


def start_server(html_content, port=8000):
    """Start a simple HTTP server to serve the review page."""
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/':
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(html_content.encode('utf-8'))
            else:
                super().do_GET()

    with socketserver.TCPServer(("", port), Handler) as httpd:
        print(f"Review viewer running at http://localhost:{port}")
        webbrowser.open(f"http://localhost:{port}")
        httpd.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path, help="Path to iteration workspace")
    parser.add_argument("--skill-name", required=True, help="Skill name for display")
    parser.add_argument("--benchmark", type=Path, help="Path to benchmark.json")
    parser.add_argument("--previous-workspace", type=Path, help="Path to previous iteration workspace")
    parser.add_argument("--static", type=Path, help="Write static HTML to file instead of starting server")
    args = parser.parse_args()

    # Generate HTML
    html = generate_html(
        args.workspace,
        args.skill_name,
        args.benchmark,
        args.previous_workspace
    )

    # Output
    if args.static:
        args.static.write_text(html, encoding="utf-8")
        print(f"Static review page written to {args.static}")
    else:
        # Start server in a thread
        server_thread = threading.Thread(target=start_server, args=(html,))
        server_thread.daemon = True
        server_thread.start()
        
        # Keep the script running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Server stopped")


if __name__ == "__main__":
    exit(main())
