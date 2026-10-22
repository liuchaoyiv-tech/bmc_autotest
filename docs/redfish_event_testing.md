# Redfish event tests

The event cases use the resource's advertised schema version and
`Actions.#EventService.SubmitTestEvent.@Redfish.ActionInfo` when available.
Event types are deprecated in modern Redfish eventing. Missing optional or
deprecated properties are not automatically firmware failures.

## Configuration

Run cases from the repository root using the usual `-i`, `-u` and `-p`
arguments. Configure `conf/bmc/event/event_test.json`:

- `TestSubDestination`: callback URL. CRUD cases may use the documentation
  address supplied in the config. **event_009 requires a real, reachable
  receiver**; its default is deliberately empty.
- `TestSubContext`: prefix for a unique context generated for each run.
- `TestSubEventTypes`: optional compatibility setting for older BMCs; omitted
  by default. Modern subscriptions use `EventFormatType: Event`.
- `TestSubHttpHeaders`: optional array of callback header objects; omitted by
  default. Use this explicitly when testing custom header delivery. The sender
  supplies its normal HTTP headers without this property.
- `TestMessageId`: optional registered message ID. By default the test discovers
  `Base.Success` and its version through the BMC's message registries.
- `TestMessageArgs`: arguments for an explicitly configured message ID.
- `TaskTimeout`: maximum seconds to wait for the event action task (default 60).

Create/query/delete cases and event_009 own their temporary subscriptions.
They identify ownership using both a unique Context and the expected
Destination, clean up even after failures, and report cleanup failures as FAIL.
They never borrow or delete unrelated subscriptions. Each case can run against
an initially empty subscription collection.

## Positive event test and SDK dependency

Use a version of redfish-python-sdk whose `submit_test_event()` returns its
`RedfishResponse`, including asynchronous task information. A release that
discards this response cannot establish task completion and causes an explicit
test failure. [SDK PR #66](https://github.com/rednote-infra/redfish-python-sdk/pull/66)
is required before releasing this change. Validate against that SDK branch until
a release containing the fix is available; stock SDK 1.3.0 discards the response.

event_009 creates a subscription, sends a valid MessageId using supported action
parameters, waits for the task to complete, then cleans up. Task exceptions,
timeouts and warning/critical completion status fail the case. A successful
HTTP 202 alone is not a passing result.

This case verifies the sender's operation and task result. For end-to-end
delivery, separately capture the receiver's POST and check its Context,
MessageId and payload. Keep the receiver active until the action finishes.

Negative cases require HTTP 400 and the expected ExtendedInfo MessageId key.
Authentication failures, transport errors, 5xx responses and different 400
errors do not count as a successful negative test.

## Offline regression checks

With pytest and the SDK installed, run `python -m pytest tests/test_redfish_event.py`.

## DMTF references

- [EventService v1.5.0](https://redfish.dmtf.org/schemas/v1/EventService.v1_5_0.json):
  EventType and EventTypesForSubscription deprecated since v1.3;
  SubmitTestEvent.MessageId is required.
- [EventDestination v1.13.0](https://redfish.dmtf.org/schemas/v1/EventDestination.v1_13_0.json):
  EventTypes deprecated since v1.5; HttpHeaders is an array of objects.
- [DSP0266](https://redfish.dmtf.org/schemas/DSP0266_1.20.1.html):
  deprecated elements, action discovery and asynchronous operation handling.
