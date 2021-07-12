# Tenable Zero Day Assessment Writeups - jiva

## Here are my writeups for each of the 4 challenges

```
Challenge 1: tenable_cli.jar
===
As much as it pains me to admit it, not every tool is written in C or C++. It's important for a vulnerability hunter to be able to handle other languages: Python, Lua, Java, Go, js, etc. This challenge is written in Java. For this task, find as many vulnerabilities in tenable_cli.jar as you can. Do not overthink this. If you are hunting outside of CLI.class then you've gone too far.

Deliverables:
1. A write up describing how you approached the hunt and found the vulnerabilities.
2. PoC scripts for each vulnerability. Please provide individual scripts for each PoC.
```

I started off this challenge by grabbing my goto jar decompiler, JD-GUI (http://java-decompiler.github.io/).

