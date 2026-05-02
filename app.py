import sys
import os

# Redirect everything to the main app in /public
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "public"))

if __name__ == "__main__":
    from public.app import main
    main()
