"""Direction 4: open new areas.

Preregistered in research/direction4_open_areas.md (b7cc862).
Sections: A COT links, C named events, D per-complex overlay.
International cracks: route 400 -> CONSTRAINED.
"""
from __future__ import annotations

import importlib.util
import csv
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "engine"
PANEL = ENGINE / "panel_v2.parquet"
COT = ENGINE / "cot"

spec = importlib.util.spec_from_file_location("fb", str(ENGINE / "factor_book.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)
spec4 = importlib.util.spec_from_file_location("b4", str(ENGINE / "engine_v2x.py"))
b4 = importlib.util.module_from_spec(spec4)
spec4.loader.exec_module(b4)

BLOCK = 20
WARMUP = 90
OOS = slice("2007-07-30", "2023-09-08")
NC = 20
NC_SEED = 23


def log(msg: str) -> None:
    print(msg, flush=True)


def normws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().upper()


def sm_expanding_mean(s: pd.Series, min_obs: int = 12) -> pd.Series:
    out = pd.Series(np.nan, index=s.index, dtype=float)
    for m in range(1, 13):
        idx = s.index[s.index.month == m]
        sub = s.loc[idx]
        cs = sub.cumsum()
        ct = sub.notna().cumsum()
        mean = cs.shift(1) / ct.shift(1)
        mean[ct.shift(1) < min_obs] = np.nan
        out.loc[idx] = mean
    return out


def sm_expanding_std(s: pd.Series, min_obs: int = 12) -> pd.Series:
    out = pd.Series(np.nan, index=s.index, dtype=float)
    for m in range(1, 13):
        idx = s.index[s.index.month == m]
        sub = s.loc[idx]
        var = ((sub - sub.expanding().mean().shift(1)).pow(2)).expanding().mean().shift(1)
        sd = var.pow(0.5)
        sd[sub.expanding().count().shift(1) < min_obs] = np.nan
        out.loc[idx] = sd
    return out


def sm_z(s: pd.Series, min_obs: int = 12) -> pd.Series:
    return ((s - sm_expanding_mean(s, min_obs)) / sm_expanding_std(s, min_obs)).clip(-8, 8)


def bucket(feat, fwd, n_q=5):
    idx = fwd.index.intersection(feat.dropna().index)
    if len(idx) < 60:
        return None
    f, r = feat.loc[idx], fwd.loc[idx]
    try:
        q = pd.qcut(f, n_q, labels=False, duplicates="drop")
    except ValueError:
        return None
    out = []
    for b in sorted(set(q.dropna())):
        sel = q == b
        out.append((b, int(sel.sum()), r[sel].mean()))
    return out


def print_b(rows, tag):
    if not rows:
        log(f"  {tag}: insufficient")
        return
    log(f"  {tag}: " + "  ".join(f"b{b}:{m*100:+.1f}%({n})" for b, n, m in rows))
    if len(rows) >= 2:
        return rows[-1][2] - rows[0][2]
    return np.nan


def main() -> None:
    df = pd.read_parquet(PANEL).sort_index()
    levels = fb.build_levels(df)
    full_idx = df.index
    fwd_crack = (levels["crack_321"].shift(-20) - levels["crack_321"]) / \
        b4.base_of(levels["crack_321"]).shift(1).replace(0.0, np.nan)
    fwd_cl = (df["CL"].shift(-20) - df["CL"]) / b4.base_of(df["CL"]).shift(1).replace(0.0, np.nan)
    rows = []

    log("=== A COT / positioning links ===")
    cot = {}
    for name, fpath, mkey, ckey, excl in (
        ("crude", COT / "raw_cot_crude_all.csv", "NEW YORK MERCANTILE",
         "CRUDE OIL, LIGHT SWEET", "E-MINI"),
        ("rbob", COT / "raw_cot_rbob_all.csv", "NEW YORK MERCANTILE",
         "GASOLINE RBOB", "SWAP|CRACK|CALENDAR|CBOB|E-MINI|FINANCIAL|SPR|UP-DOWN")):
        raw = pd.read_csv(fpath)
        mk = raw["market_and_exchange_names"].map(normws)
        ck = raw["contract_market_name"].map(normws)
        keep = mk.str.contains(mkey, na=False, regex=False) & ck.str.contains(ckey, na=False, regex=False) \
            & ~ck.str.contains(excl, na=False, regex=True)
        sub = raw[keep].copy()
        sub["date"] = pd.to_datetime(sub["report_date_as_yyyy_mm_dd"].astype(str), errors="coerce")
        sub = sub.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")
        net = (pd.to_numeric(sub["m_money_positions_long_all"], errors="coerce")
               - pd.to_numeric(sub["m_money_positions_short_all"], errors="coerce")).dropna()
        net.index = sub["date"][net.index] if False else net
        net = pd.Series(net.to_numpy(), index=sub["date"].iloc[:len(net)])
        net = net[~net.index.duplicated(keep="last")].sort_index()
        cot[name] = net
        log(f"  {name} COT rows {len(net)} {net.index.min().date()}..{net.index.max().date()}"
            f" net mean {net.mean():+.0f}")
        # availability: report Tue + 4 days release, then +1 day trade lag, ffill daily
        avail = net.copy()
        avail.index = avail.index + pd.Timedelta(days=5)
        daily = avail.reindex(avail.index.union(full_idx)).sort_index().ffill().reindex(full_idx)
        nz = sm_z(daily)
        chg = sm_z(daily.diff())
        for tag, f, lvl in (("crack", fwd_crack, "crack_321"), ("CL", fwd_cl, "CL")):
            d = print_b(bucket(nz, f), f"COT net z vs fwd20 {lvl}")
            ch = print_b(bucket(chg, f), f"COT chg z vs fwd20 {lvl}")
            if d is not None:
                rows.append({"item": "cot", "inst": name, "target": lvl, "net_delta": d,
                             "chg_delta": ch})
    # control on rbob net z vs crack (crude constrained: no NYMEX series)
    if "rbob" in cot and len(cot["rbob"]):
        net = cot["rbob"]
        avail = net.copy(); avail.index = avail.index + pd.Timedelta(days=5)
        daily = avail.reindex(avail.index.union(full_idx)).sort_index().ffill().reindex(full_idx)
        nz = sm_z(daily)
        real = print_b(bucket(nz, fwd_crack), "rbob COT net z (real) vs fwd20 crack")
        nc = []
        for i in range(NC):
            rng = np.random.default_rng(NC_SEED + i)
            lab = rng.random(len(full_idx)) < 0.2
            nc.append(fwd_crack[lab & fwd_crack.notna()].mean())
        log(f"  control: net_z top-bottom {real} vs random-slice mean {np.mean(nc):.4f} "
            f"sd {np.std(nc):.4f}")
        rows.append({"item": "cot_control", "real_delta": real, "shuf_mean": float(np.mean(nc))})

    log("\n=== C named events (20d forward) ===")
    events = [
        ("hurricane_ike", "2008-09-01"), ("hurricane_isaac", "2012-08-28"),
        ("hurricane_harvey", "2017-08-25"), ("hurricane_ida", "2021-08-29"),
        ("tx_freeze", "2021-02-13"), ("opec_2014", "2014-11-27"),
        ("opec_2016", "2016-11-30"), ("opec_2020_mar", "2020-03-06"),
        ("opec_2020_apr", "2020-04-12"), ("opec_2022", "2022-10-05"),
        ("covid_pandemic", "2020-03-11"), ("neg_wti", "2020-04-20"),
    ]
    uncond = fwd_crack.loc[OOS].dropna().mean()
    log(f"  unconditional OOS fwd20 mean {uncond*100:+.2f}%")
    for name, dstr in events:
        t = pd.Timestamp(dstr)
        if t not in full_idx:
            t = full_idx[full_idx.searchsorted(t)]
        seg = fwd_crack.loc[t:t + pd.Timedelta(days=39)].dropna()
        m = seg.mean() if len(seg) else np.nan
        log(f"  {name:<18} {dstr} fwd20 {m*100 if m==m else 0:+.2f}% n={len(seg)}")
        rows.append({"item": "event", "event": name, "date": dstr, "fwd20": m})

    log("\n=== D per-complex overlay ===")
    fac4, rets4, turn4 = b4.build_v4(levels, None)
    names = ["crack_321", "cross_sectional", "bzwti"]
    net_w = b4.apply_costs({k: fac4[k] for k in names}, {k: rets4[k] for k in names},
                           turnover={k: turn4[k] for k in names})
    book_w = b4.book_returns(net_w, names, b4.weight_scheme(net_w[names], "EQ"))
    # Brent legs
    bz = df["BZ"].astype(float)
    blevels = {"brent321": (2 * df["RB"] + df["HO"]) / 3 * 42 - bz,
               "brent_gas": df["RB"] * 42 - bz, "brent_ho": df["HO"] * 42 - bz}

    def state_machine(z, enter=-0.75, exit_=-0.5):
        zz = z.to_numpy(dtype=float)
        vals = np.zeros(len(z), dtype=float)
        state = 0.0
        for i in range(len(z)):
            if np.isnan(zz[i]):
                vals[i] = 0.0
                continue
            if state == 0.0 and zz[i] <= enter:
                state = 1.0
            elif state == 1.0 and zz[i] >= exit_:
                state = 0.0
            vals[i] = state
        return pd.Series(vals, index=z.index)

    pos_b, ret_b, turn_b = {}, {}, {}
    z5 = fb.seasonal_z(blevels["brent321"])
    sig5 = state_machine(z5)
    raw5 = sig5 * b4.fixed_vol_scale(blevels["brent321"], fb.VT_F1)
    pos_b["brent321"] = b4.leg_risk(raw5, blevels["brent321"], trailing_stop=False).fillna(0.0)
    base = b4.base_of(blevels["brent321"]).shift(1).replace(0.0, np.nan)
    ret_b["brent321"] = (pos_b["brent321"].shift(1).fillna(0.0) * blevels["brent321"].diff() / base).fillna(0.0)
    turn_b["brent321"] = pos_b["brent321"].diff().abs().fillna(0.0)
    # F6 cross most-crushed among brent legs
    zdf = pd.DataFrame({k: fb.seasonal_z(blevels[k]) for k in blevels})
    valid = zdf.notna().all(axis=1)
    chosen = pd.Series(np.nan, index=zdf.index, dtype=float)
    arr = zdf.to_numpy(dtype=float)
    cols = list(zdf.columns)
    for i in range(len(zdf)):
        if valid.iloc[i]:
            row = arr[i]
            if np.isnan(row).all():
                continue
            k = cols[int(np.nanargmin(row))]
            if row[int(np.nanargmin(row))] < fb.XS_MIN_Z:
                chosen.iloc[i] = list(blevels).index(k)
    leg_p, leg_r, leg_t = {}, {}, {}
    for li, leg in enumerate(blevels):
        lvl = blevels[leg]
        on = chosen == li
        raw = (pd.Series(1.0, index=lvl.index).where(on, 0.0)
               * b4.fixed_vol_scale(lvl, fb.VT_F2))
        p = b4.leg_risk(raw, lvl, trailing_stop=False).fillna(0.0)
        base = b4.base_of(lvl).shift(1).replace(0.0, np.nan)
        leg_p[leg] = p
        leg_r[leg] = (p.shift(1).fillna(0.0) * lvl.diff() / base).fillna(0.0)
        leg_t[leg] = p.diff().abs().fillna(0.0)
    pos_b["brent_xs"] = pd.DataFrame(leg_p).sum(axis=1)
    ret_b["brent_xs"] = pd.DataFrame(leg_r).sum(axis=1).fillna(0.0)
    turn_b["brent_xs"] = pd.DataFrame(leg_t).sum(axis=1)
    net_b = b4.apply_costs(pos_b, ret_b, turnover=turn_b)
    book_b = b4.book_returns(net_b, ["brent321", "brent_xs"],
                             b4.weight_scheme(net_b[["brent321", "brent_xs"]], "EQ"))
    # champion (book overlay)
    comb_all = (book_w + book_b) / 2
    book_all_ov = b4.apply_overlay(book_w + book_b)
    # two-sleeve: overlay each sleeve, combine 50/50
    wov = b4.apply_overlay(book_w)
    bov = b4.apply_overlay(book_b)
    two = (wov + bov) / 2
    for tag, ser in (("champion", b4.apply_overlay(book_w)),
                     ("book_ov_all", book_all_ov),
                     ("two_sleeve", two),
                     ("book_ov_FULL", b4.apply_overlay((book_w + book_b) / 1))):
        so = b4.stats(ser.loc[OOS].iloc[WARMUP:] if len(ser.loc[OOS]) > WARMUP else ser.loc[OOS])
        log(f"  {tag:<14} OOS ov Sh {so['sharpe']:.3f} CAGR {so['cagr']*100:.2f}% "
            f"DD {so['maxdd']*100:.2f}% worst {so['worst_day']*100:.2f}%")
        rows.append({"item": "sleeve", "variant": tag, "sharpe": so["sharpe"],
                     "cagr": so["cagr"], "dd": so["maxdd"]})

    with open(ROOT / "results" / "direction4.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r}))
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})
    log("\nSaved results/direction4.csv")


if __name__ == "__main__":
    main()
