"""Show the market observations, deterministic results, and model explanation."""

from datetime import timezone

import streamlit as st

from .model_settings import bedrock_failure_message


_FEED_LABEL = {
    "iex": "IEX single-exchange feed",
    "sip": "SIP consolidated feed",
    "delayed_sip": "SIP consolidated feed with a 15-minute delay",
}


def _utc_time(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _show_verified_market(analysis, show_history, history_error):
    quote = analysis.quote
    st.metric("Latest eligible trade", f"{quote.currency} {quote.price:,f}")
    st.caption(f"{_FEED_LABEL[quote.feed]} · trade {_utc_time(quote.as_of)} · retrieved {_utc_time(quote.retrieved_at)}")
    st.markdown(f"[Quote source · {quote.source}]({quote.source_url})")
    if analysis.indicative_notional is not None:
        st.metric("Indicative purchase cost", f"{quote.currency} {analysis.indicative_notional:,.2f}")
        st.caption("Share quantity multiplied by the observed trade price, before fees. Execution price can differ.")
    if trailing := analysis.trailing:
        st.subheader("Verified historical movement")
        first, second = st.columns(2)
        first.metric("Price return", f"{trailing.price_return:.2%}")
        second.metric("Maximum drawdown", f"{trailing.max_drawdown:.2%}")
        st.caption(f"{trailing.start} to {trailing.end} · {trailing.observations} daily closes · {trailing.adjustment} adjustment")
        st.markdown(f"[History source]({trailing.source_url}) · [Trading calendar]({trailing.calendar_source_url})")
    elif show_history and (history_error or analysis.history_withheld_reason):
        st.info(history_error or analysis.history_withheld_reason)


def render_live_market_result(result):
    intake = result["intake"]
    status = intake["status"]
    if status != "ready":
        message = intake.get("message")
        if not message:
            message = ("Live analysis supports read-only market research. Enter a fictional purchase or ask for an observed price."
                       if status == "unsupported" else "State one U.S. stock ticker and the market information you want to analyze.")
        st.warning(message)
        return

    ticker, shares = intake["symbol"], intake.get("shares")
    st.subheader(f"Proposed purchase of {ticker}" if shares else f"Market data for {ticker}")
    if shares:
        st.text(f"Requested quantity · {shares} shares")
    if intake.get("origin") == "local":
        st.caption(f"{bedrock_failure_message(intake.get('trace', ()))} The request used local interpretation.")
    if result["market_error"]:
        st.warning(result["market_error"])
    else:
        _show_verified_market(result["analysis"], intake["scope"] == "quote_and_history", result["history_error"])
        summary = result["summary"]
        if summary["status"] == "ready":
            st.subheader("Model interpretation")
            st.write(summary["conclusion"])
        else:
            st.caption("Model interpretation is unavailable. The verified market figures are shown above.")

    with st.expander("Request and verification details"):
        if wording := intake.get("wording"):
            st.text(wording)
        if analysis := result["analysis"]:
            st.json(analysis.as_model_evidence(), expanded=False)
