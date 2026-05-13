# Video Social Pipeline

A Python project for generating video scripts, route modeling, and publish decisions.

## Installation

No external dependencies required. Uses Python standard library only.

## Usage

```python
from video_social import make_script, route_model, publish_decision

# Generate a script
result = make_script('product short')
print(result['script'])
print(result['storyboard'])

# Route model
print(route_model('instagram reel'))

# Publish decision (always returns executed=False)
print(publish_decision())
```

## Testing

Run tests with pytest:

```bash
pytest tests/
```

## LARGESTACK Integration

To run the LARGESTACK smoke test (requires `largestack` package):

```bash
python -c "import asyncio; from largestack_app import run_largestack_smoke; print(asyncio.run(run_largestack_smoke()))"
```
