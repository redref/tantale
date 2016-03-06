# Tantale

[![Build Status](https://travis-ci.org/redref/tantale.svg?branch=master)](https://travis-ci.org/redref/tantale) [![Coverage Status](https://coveralls.io/repos/github/redref/tantale/badge.svg?branch=master)](https://coveralls.io/github/redref/tantale?branch=master)

## Overview

Home-brewed project to join Livestatus compatible GUI's to modern database possibilities.

Got this idea googling about monitoring GUI's handling custom backends, and did'nt find anything suitable.

Guidelines
  * keep it simple - each funtionnality must remain REALLY understandable
  * ...

Project objectives are first
  * livestatus socket : get query, translate it into DB query (with abstraction on backends)
  * elasticsearch backend
  * checks socket : receive checks results, store into DB

Then, ideas :
  * poller thread : handle active checks, main objective is passive based
  * checks socket : process notifications / plugins / ...

## Inspirations

  * [Diamond](https://github.com/python-diamond/Diamond)
  * [Graphite - Carbon](https://github.com/graphite-project/carbon)