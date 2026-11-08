# Records docs/demo.gif, the demo shown in the README.
#   brew install vhs
#   vhs docs/demo.tape          (run from the repo root; a real run costs about $0.50)
# Uses the sample project and --no-deploy, so nothing is pushed anywhere.

Output docs/demo.gif

Require make

Set Shell "bash"
Set FontSize 15
Set Width 1300
Set Height 760
Set Padding 20
Set Theme "Catppuccin Mocha"
Set TypingSpeed 35ms
Set Framerate 24
# The agents need about a minute. Play the recording twice as fast so the GIF stays short.
Set PlaybackSpeed 2

# Setup the viewer doesn't need to see: a clean prompt and a fresh copy of the sample project.
Hide
Type `export PATH="$PWD/.venv/bin:$PATH" PS1='$ ' BASH_SILENCE_DEPRECATION_WARNING=1`
Enter
Type `make -s demo-repo DEMO=/tmp/devagent-demo >/dev/null && clear`
Enter
Sleep 3s
Show

Type `devagent run "Add a slugify(text) function to sample/text.py, with tests" --repo /tmp/devagent-demo --no-deploy`
Sleep 1.5s
Enter

# Gate 1: wait for the plan, give the viewer a moment to see it, then approve.
# Wait on the cursor line (not +Screen): the plan is taller than the screen, and the question ends in "(a):".
Wait@5m /\(a\):/
Sleep 4s
Type "a"
Sleep 800ms
Enter

# Coder, Tester, test run, cost table. Wait until the shell prompt comes back.
Wait@10m /^\$\s*$/
Sleep 8s
