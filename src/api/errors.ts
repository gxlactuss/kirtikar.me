export class HttpError extends Error {
  constructor(
    readonly status: number,
    readonly body: string,
  ) {
    super(`HTTP ${status}: ${body.slice(0, 200)}`);
    this.name = 'HttpError';
  }
}

export class NetworkError extends Error {
  constructor(message = 'The network request failed') {
    super(message);
    this.name = 'NetworkError';
  }
}

export class TimeoutError extends Error {
  constructor(message = 'The request timed out') {
    super(message);
    this.name = 'TimeoutError';
  }
}

/**
 * A sleeping Hugging Face Space answers with its own HTML "starting up"
 * page, not JSON. Parsing that yields a confusing SyntaxError, so the health
 * check and every JSON read verify the content type first and raise this.
 */
export class NotJsonError extends Error {
  constructor(readonly contentType: string | null) {
    super(`Expected JSON but the server sent ${contentType ?? 'nothing'}`);
    this.name = 'NotJsonError';
  }
}
