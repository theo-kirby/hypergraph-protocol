---
node_id: 9810511f-edb5-563f-a7c6-320bc6e11516
slug: brave-otter-1002
title: Prototyped CSV ingest; hit an OOM wall
created_at: '2026-08-02T01:00:00+00:00'
parents:
- wise-anchor-1001
summary: ''
---
## What

Built the first ingest prototype and measured it on a 2.3GB CSV.

## Why

Root of an independent workstream: nothing ingests data yet.

## Method

`python ingest.py --input big.csv`, pandas chunked reader, chunksize=100k.

## Result

OOM at 6.1GB RSS on a 4GB box. The chunked reader still materializes the whole
frame at concat time; this approach is dead without a memory budget.

## State Impact

- target: NEW ingest — new component covering CSV ingest, status open
