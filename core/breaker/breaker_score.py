class BreakerScore:

    def calculate(

        self,

        order_block_score,

    ):

        return min(

            100,

            order_block_score + 10,

        )