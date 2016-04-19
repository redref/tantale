ctx._source.last_check = timestamp
ctx._source.output = output
ctx._source.contacts = contacts

if (ctx._source.status != status) {
    ctx._source.status = status
    ctx._source.timestamp = timestamp
    ctx._source.output = output
    if (ctx._source.ack == 1) {
        ctx._source.ack = 0
    }
}
