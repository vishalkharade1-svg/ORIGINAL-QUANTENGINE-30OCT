from analytics.trade import Trade
from analytics.trade_journal import TradeJournal
from analytics.performance import Performance


journal = TradeJournal()

journal.add(

    Trade(

        symbol="BTCUSDT",

        side="BUY",

        quantity=2,

        entry=64000,

        exit=64200,

        pnl=400,

        strategy="ICT",

        win=True,

    )

)

journal.add(

    Trade(

        symbol="ETHUSDT",

        side="SELL",

        quantity=5,

        entry=3500,

        exit=3520,

        pnl=-100,

        strategy="ICT",

        win=False,

    )

)

journal.add(

    Trade(

        symbol="SOLUSDT",

        side="BUY",

        quantity=10,

        entry=160,

        exit=168,

        pnl=80,

        strategy="Swing",

        win=True,

    )

)

Performance().report(journal)