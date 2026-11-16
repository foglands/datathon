"""Developer-only workbench: streamlit run validation_app.py.

The customer entry point is app.py and exposes no validation navigation.
"""

from app import main


if __name__ == "__main__":
    main(validation=True)
