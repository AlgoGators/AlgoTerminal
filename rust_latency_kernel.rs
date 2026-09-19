//! Minimal FFI kernel for the measured daily accounting seam.
//!
//! The caller owns the signal and risk path. This function only reproduces
//! engine_v2.apply_costs followed by an equal or caller-supplied book sum.

use std::slice;

#[no_mangle]
pub unsafe extern "C" fn account_book(
    positions: *const f64,
    returns: *const f64,
    turnover: *const f64,
    weights: *const f64,
    rows: usize,
    factors: usize,
    trade_bps: f64,
    roll_bps: f64,
    output: *mut f64,
) -> i32 {
    if positions.is_null()
        || returns.is_null()
        || turnover.is_null()
        || weights.is_null()
        || output.is_null()
    {
        return -1;
    }

    let positions = slice::from_raw_parts(positions, rows * factors);
    let returns = slice::from_raw_parts(returns, rows * factors);
    let turnover = slice::from_raw_parts(turnover, rows * factors);
    let weights = slice::from_raw_parts(weights, factors);
    let output = slice::from_raw_parts_mut(output, rows);
    let trade_rate = trade_bps / 10_000.0;
    let roll_rate = roll_bps / 252.0 / 10_000.0;

    for day in 0..rows {
        let mut book = 0.0;
        for factor in 0..factors {
            let offset = factor * rows + day;
            let daily_return = returns[offset];
            // pandas applies fillna(0) after the whole expression. A missing
            // return therefore produces zero and does not charge costs.
            if daily_return.is_nan() {
                continue;
            }
            let position = if positions[offset].is_nan() {
                0.0
            } else {
                positions[offset]
            };
            let daily_turnover = if turnover[offset].is_nan() {
                0.0
            } else {
                turnover[offset]
            };
            let net = daily_return
                - trade_rate * daily_turnover
                - roll_rate * position.abs();
            book += weights[factor] * net;
        }
        output[day] = book;
    }
    0
}
