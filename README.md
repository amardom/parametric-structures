# parametric-structures

Parametric studies for architectural design. Each JSON case defines a geometry and analysis. Python generates SVG drawings, a STEP model and an Elmer result. The static website compares precomputed variants in an interactive viewer.

The models use beams and hangers, shells or 3D solids as appropriate. Structural cases cover static response, harmonic response and concrete volume optimisation. The thermal case couples transient 1D heat conduction through the envelope to an indoor-air energy balance.

<https://parametric-structures.pages.dev/>

## Run

Use Linux or WSL with Python 3.12 and ElmerSolver and ElmerGrid available on PATH. Cases with custom Fortran elements also require Elmer's development tools, including `elmerf90`, and a Fortran compiler. The build downloads the upstream Elmer shell source for those cases.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python main.py projects/shelter/concrete-shelter.json
```

Pass another case JSON to run a different model, or add `--plans-only` to generate just the drawings. To build and serve the portfolio locally:

```sh
python website/build_data.py
python -m http.server 8112 --directory website
```

## Tests

```sh
python -m pytest -q
python -m pytest -q -m "not elmer"
```

The second command runs the suite without launching Elmer.

Generate the website before running the Chromium test.

```sh
python -m playwright install chromium
python -m pytest -q -m browser
```
