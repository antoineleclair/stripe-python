# -*- coding: utf-8 -*-
# File generated from our OpenAPI spec
from stripe import api_requestor, util
from stripe.api_resources.abstract import APIResource
from typing import ClassVar
from typing_extensions import Literal


class UsageRecord(APIResource["UsageRecord"]):
    """
    Usage records allow you to report customer usage and metrics to Stripe for
    metered billing of subscription prices.

    Related guide: [Metered billing](https://stripe.com/docs/billing/subscriptions/metered-billing)
    """

    OBJECT_NAME: ClassVar[Literal["usage_record"]] = "usage_record"
    id: str
    livemode: bool
    object: Literal["usage_record"]
    quantity: int
    subscription_item: str
    timestamp: int

    @classmethod
    def create(
        cls,
        api_key=None,
        idempotency_key=None,
        stripe_version=None,
        stripe_account=None,
        **params
    ):
        if "subscription_item" not in params:
            raise ValueError("Params must have a subscription_item key")

        subscription_item = params.pop("subscription_item")

        requestor = api_requestor.APIRequestor(
            api_key, api_version=stripe_version, account=stripe_account
        )
        url = "/v1/subscription_items/%s/usage_records" % subscription_item
        headers = util.populate_headers(idempotency_key)
        response, api_key = requestor.request("post", url, params, headers)

        return util.convert_to_stripe_object(
            response, api_key, stripe_version, stripe_account
        )
