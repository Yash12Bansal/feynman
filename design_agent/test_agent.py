#!/usr/bin/env python3
"""
Test script for the Diagram Design Agent.

Usage:
  python test_agent.py "Draw a single slit diffraction pattern"
  python test_agent.py --interactive
  python test_agent.py --examples
"""

import argparse
import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.agent import DiagramAgent


EXAMPLE_PROMPTS = [
    "Draw a single slit diffraction pattern with an intensity graph",
    "Show a quadratic function y = ax^2 + bx + c with sliders for a, b, c",
    "Draw a simple pendulum with the forces acting on it",
    "Show the chemical reaction: 2H2 + O2 -> 2H2O with molecular diagrams",
    "Draw a right triangle with the Pythagorean theorem labeled",
    "Show Snell's law of refraction with a draggable angle of incidence",
    "Draw an electric circuit with a battery, resistor, and capacitor in series",
    "Plot sin(x), cos(x), and tan(x) on the same coordinate plane",
    "Show the unit circle with angle theta and its sine/cosine projections",
    "Draw a convex lens ray diagram showing image formation",
]


def run_single(prompt: str, save_to: str = None):
    """Generate a diagram from a single prompt."""
    agent = DiagramAgent()
    print(f"\n{'=' * 60}")
    print(f"Prompt: {prompt}")
    print(f"{'=' * 60}")
    print("Generating diagram...\n")

    try:
        result = agent.generate_sync(prompt)
        spec = result.model_dump(by_alias=True, exclude_none=True)
        output = json.dumps(spec, indent=2)

        print(f"Title: {spec.get('title', 'Untitled')}")
        print(f"Elements: {len(spec.get('elements', []))}")
        print(f"Parameters: {len(spec.get('parameters', []))}")
        print(f"\nFull spec:\n{output}")

        if save_to:
            with open(save_to, "w") as f:
                f.write(output)
            print(f"\nSaved to: {save_to}")

        return spec
    except Exception as e:
        print(f"Error: {e}")
        return None


def run_interactive():
    """Interactive mode - keep prompting."""
    agent = DiagramAgent()
    print("\nDiagram Design Agent - Interactive Mode")
    print("Type 'quit' to exit, 'examples' to see example prompts\n")

    while True:
        try:
            prompt = input("Prompt> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not prompt:
            continue
        if prompt.lower() == "quit":
            break
        if prompt.lower() == "examples":
            print("\nExample prompts:")
            for i, ex in enumerate(EXAMPLE_PROMPTS, 1):
                print(f"  {i}. {ex}")
            print()
            continue

        # Allow selecting by number
        if prompt.isdigit() and 1 <= int(prompt) <= len(EXAMPLE_PROMPTS):
            prompt = EXAMPLE_PROMPTS[int(prompt) - 1]
            print(f"Using: {prompt}")

        print("Generating...\n")
        try:
            result = agent.generate_sync(prompt)
            spec = result.model_dump(by_alias=True, exclude_none=True)
            print(json.dumps(spec, indent=2))
            print(
                f"\n[{spec.get('title', 'Untitled')} | "
                f"{len(spec.get('elements', []))} elements | "
                f"{len(spec.get('parameters', []))} parameters]\n"
            )
        except Exception as e:
            print(f"Error: {e}\n")


def run_api_test(prompt: str):
    """Test via the FastAPI endpoint (server must be running)."""
    import urllib.request
    import urllib.error

    url = "http://localhost:8000/api/generate"
    data = json.dumps({"prompt": prompt}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )

    print(f"POST {url}")
    print(f"Prompt: {prompt}\n")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
            print(json.dumps(result, indent=2))
    except urllib.error.URLError as e:
        print(f"Error: {e}")
        print("Is the backend server running? Start it with:")
        print("  cd backend && python -m backend.main")


def main():
    parser = argparse.ArgumentParser(description="Test the Diagram Design Agent")
    parser.add_argument("prompt", nargs="?", help="Diagram prompt")
    parser.add_argument(
        "--interactive", "-i", action="store_true", help="Interactive mode"
    )
    parser.add_argument(
        "--examples", "-e", action="store_true", help="Show example prompts"
    )
    parser.add_argument("--save", "-s", help="Save output to file")
    parser.add_argument(
        "--api",
        action="store_true",
        help="Test via API endpoint instead of direct agent call",
    )

    args = parser.parse_args()

    if args.examples:
        print("Example prompts:")
        for i, ex in enumerate(EXAMPLE_PROMPTS, 1):
            print(f"  {i}. {ex}")
        return

    if args.interactive:
        run_interactive()
        return

    if args.prompt:
        if args.api:
            run_api_test(args.prompt)
        else:
            run_single(args.prompt, save_to=args.save)
        return

    # Default: run with a sample prompt
    run_single(
        "Draw a single slit diffraction pattern with an intensity vs angle graph"
    )


if __name__ == "__main__":
    main()
