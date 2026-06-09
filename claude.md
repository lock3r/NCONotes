# NCO Notes Project Guidelines 

VENV: ~/.virtualenvs/NCONotes/
Activate with: `source ~/.virtualenvs/NCONotes/bin/activate`

You need to activate the venv to run tests and code.

Python Dependencies: we use Poetry.

CRITICAL: poetry is installed INSIDE the venv. We NEVER contaminate the system install with anything. 
CRITICAL: Poetry is installed INSIDE the venv (~/.virtualenvs/NCONotes/bin/poetry). 
Never run `pip install` or `pip3 install` directly. Always use `poetry add`.