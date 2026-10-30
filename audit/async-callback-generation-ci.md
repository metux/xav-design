# Asynchronous backend callback generation annotations

The native-backend CI gate runs `tools/check-async-callback-generations.py`
over every tracked C/C++ source/header, Rust `.rs`, and Zig `.zig` file. A source file containing an
asynchronous submission, wait, completion, fence, semaphore, or callback
registration signal is not allowed to pass merely because it compiles.

Each asynchronous callback must have two adjacent, reviewable annotations in
its source file:

```c
/* XAV_ASYNC_CALLBACK_REGISTER: on_submit_done; device_generation; resource_generation; recording_epoch */
/* XAV_ASYNC_CALLBACK_VALIDATE: on_submit_done; device_generation; resource_generation; recording_epoch */
void on_submit_done(struct callback_context *ctx)
{
    if (ctx->device_generation != current_device_generation(ctx->device))
        return;
    if (ctx->resource_generation != current_resource_generation(ctx->resource))
        return;
    if (ctx->recording_epoch != current_recording_epoch(ctx->command_buffer))
        return;
    /* terminalize only the captured operation and release its captured refs */
}
submit_async(..., on_submit_done, captured_context);
```

The annotation lists are semicolon-separated C identifiers. The REGISTER
annotation records the immutable values captured at operation acceptance.
The VALIDATE annotation records the values checked before publishing state,
events, or releasing references. Every callback must capture and validate
`device_generation`. Every generation listed at registration must also be
listed at validation and must be consumed in a comparison or a recognizable
current-generation validation helper in the callback body.

The checker also applies contextual minimums: a callback body that refers to
buffers, memory, fences, semaphores, swapchains, images, or resources must
capture `resource_generation`; one that refers to command buffers or recording
state must capture `recording_epoch`. These checks intentionally fail closed:
unrecognized callback patterns or missing annotations require explicit review
and a checker/test update, not a silent pass.

For Rust and Zig, the checker recognizes named `fn` callback definitions and
language-specific asynchronous signals (including Rust `async fn`, `.await`,
Tokio/thread spawning, and Zig thread spawning / `@asyncCall`). Callback
closures and anonymous async blocks are not independently modeled: bind them to
a named callback function and annotate that function. The scanner is lexical,
not an AST or borrow-checker analysis, and its signal patterns must be extended
when a backend adopts a new async runtime or callback convention.

The annotations are an auditable contract, not a formal proof of concurrency
correctness. Reviewers must still verify that registration captures the actual
immutable object/generation (not a later XID lookup), that validation is
performed against the current object, and that stale callbacks release only
their own retained references. Native runtime regressions must cover XID reuse,
Device recreation, resource replacement, and command-buffer rerecording.

When new asynchronous APIs or callback naming conventions are introduced,
extend the signal patterns and negative/positive regression vectors in
`tests/test_async_callback_generation_audit.py`. Do not suppress a source
from the audit merely because the checker does not yet understand its syntax.
