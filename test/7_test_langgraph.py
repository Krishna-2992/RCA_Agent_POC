from src.graph.workflow import graph


state = {

    "user_query":

    """
    Payment Gateway transactions are failing
    with timeout errors after yesterday deployment
    """

}



result = graph.invoke(
    state
)



print(
    "\n========== FINAL RESULT =========="
)


if result.get(
    "needs_human_input"
):


    print(
        result[
            "final_response"
        ]
    )


else:


    rca = result[
        "rca_result"
    ]


    print(
        "\nROOT CAUSE:"
    )


    print(
        rca[
            "root_cause"
        ]
    )


    print(
        "\nCONFIDENCE:"
    )


    print(
        rca[
            "confidence_score"
        ]
    )