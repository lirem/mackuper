#!/usr/bin/env python3
"""Development server runner"""
import os
from app import create_app

if __name__ == '__main__':
    # Use development config for local testing
    app = create_app('development')

    # Run development server
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
