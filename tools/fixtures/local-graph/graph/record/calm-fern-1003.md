---
node_id: c81c93df-c528-50a9-9337-0af5469f71d9
slug: calm-fern-1003
title: Streaming parser fixed multi-GB ingest
created_at: '2026-08-02T02:00:00+00:00'
parents:
- brave-otter-1002
summary: ''
---
## What

Replaced the pandas path with a streaming csv parser.

## Why

Follows directly from the OOM measured in the prototype.

## Method

`python ingest.py --input big.csv --streaming`, stdlib `csv` + a row-wise validator.

## Result

2.3GB ingested in 84s at 210MB peak RSS. Ingest is working.

## State Impact

- target: quiet-summit-2002 — status open → working; OOM becomes negative knowledge
