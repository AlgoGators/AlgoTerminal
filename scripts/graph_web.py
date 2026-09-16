"""Curated idea-graph CLI for the v2 relation map.

Reads research/graph/{nodes,edges,chains}.csv and answers graph
questions: list chains, neighbors, shortest paths between concepts,
hub concepts shared across chains, and orphan nodes.

Usage:
  python graph_web.py chains
  python graph_web.py neighbors <node>
  python graph_web.py path <a> <b>
  python graph_web.py hubs
  python graph_web.py orphans
  python graph_web.py evidence
  python graph_web.py explain <node>
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).resolve().parent.parent
G = ROOT / "research" / "graph"


def load() -> tuple[nx.DiGraph, dict, dict]:
    nodes = {}
    with open(G / "nodes.csv", newline="") as f:
        for r in csv.DictReader(f):
            nodes[r["id"]] = r
    edges = []
    with open(G / "edges.csv", newline="") as f:
        for r in csv.DictReader(f):
            edges.append(r)
    chains = {}
    with open(G / "chains.csv", newline="") as f:
        for r in csv.DictReader(f):
            chains[r["id"]] = r
    dg = nx.DiGraph()
    for nid, meta in nodes.items():
        dg.add_node(nid, label=meta.get("label", nid), kind=meta.get("kind", ""))
    for e in edges:
        dg.add_edge(e["source"], e["target"], relation=e["relation"],
                    chain=e["chain"], evidence=e["evidence"], status=e["status"])
    return dg, nodes, chains


def find(dg, tok: str) -> str:
    for nid in dg.nodes:
        if tok == nid or tok == dg.nodes[nid]["label"] or tok in nid:
            return nid
    return None


def show_chain(chain_id: str, chains, dg) -> None:
    c = chains.get(chain_id)
    if not c:
        return
    print(f"\n{chain_id}  {c['name']}  [{c['status']}]")
    print(f"  source: {c['source_finding']}")
    for a, b, d in dg.edges(data=True):
        if d["chain"] == chain_id:
            print(f"  {a} --{d['relation']}-> {b}  "
                  f"[{d['evidence']}/{d['status']}]")


def main() -> None:
    dg, nodes, chains = load()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "chains"
    if cmd == "chains":
        for cid in chains:
            show_chain(cid, chains, dg)
        return
    if cmd == "neighbors":
        n = find(dg, sys.argv[2])
        if not n:
            print("node not found"); return
        ins = [(u, v, d) for u, v, d in dg.in_edges(n, data=True)]
        outs = [(u, v, d) for u, v, d in dg.out_edges(n, data=True)]
        print(f"{n}: {dg.nodes[n]['label']} ({dg.nodes[n]['kind']})")
        for u, v, d in outs:
            print(f"  {n} --{d['relation']}-> {v} [{d['chain']}]")
        for u, v, d in ins:
            print(f"  {u} --{d['relation']}-> {n} [{d['chain']}]")
        return
    if cmd == "path":
        a, b = find(dg, sys.argv[2]), find(dg, sys.argv[3])
        if not a or not b:
            print("node not found"); return
        try:
            p = nx.shortest_path(dg.to_undirected(), a, b)
        except nx.NetworkXNoPath:
            print("no path"); return
        print(" -> ".join(p))
        for i in range(len(p) - 1):
            for u, v, d in dg.edges(data=True):
                if {u, v} == {p[i], p[i + 1]}:
                    print(f"    {u} --{d['relation']}-> {v} [{d['chain']}]")
        return
    if cmd == "hubs":
        deg = sorted(dg.degree, key=lambda x: -x[1])[:8]
        for nid, d in deg:
            chains_hit = sorted({d2["chain"] for _, _, d2 in
                                 list(dg.in_edges(nid, data=True)) +
                                 list(dg.out_edges(nid, data=True))})
            print(f"{nid:<18} deg {d:>2} chains {','.join(chains_hit)}")
        return
    if cmd == "orphans":
        for nid in dg.nodes:
            if dg.degree(nid) == 0:
                print(f"{nid}  {dg.nodes[nid]['kind']}  {dg.nodes[nid]['label']}")
        return
    if cmd == "evidence":
        for a, b, d in dg.edges(data=True):
            if d["status"] not in ("untested",):
                print(f"{a} --{d['relation']}-> {b} [{d['evidence']}/{d['status']}] {d['chain']}")
        return
    if cmd == "explain":
        n = find(dg, sys.argv[2])
        if not n:
            print("node not found"); return
        print(f"{n}: {dg.nodes[n]['label']} ({dg.nodes[n]['kind']})")
        for u, v, d in dg.out_edges(n, data=True):
            print(f"  influences -> {v} [{d['chain']}]")
        for u, v, d in dg.in_edges(n, data=True):
            print(f"  <- {u} [{d['chain']}]")
        return
    print(__doc__)


if __name__ == "__main__":
    main()
