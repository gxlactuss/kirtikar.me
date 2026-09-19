import { HttpError, NetworkError, NotJsonError, TimeoutError } from './errors';
import type {
  HealthResponse,
  Listing,
  ListingPatch,
  ListingStatusResponse,
  MediaUploadResponse,
} from './types';

/**
 * No trailing slash; the client appends full paths.
 *
 * A blank value is treated as unset, not as "same origin". CI injects this
 * from a repository variable, and an unset variable arrives as `''` rather
 * than undefined — which `??` would happily accept, turning every call into
 * a relative URL against the Pages site and failing as HTML-not-JSON instead
 * of as an obvious misconfiguration.
 */
export const API_BASE: string = (
  import.meta.env.VITE_API_BASE?.trim() || 'http://localhost:8000'
).replace(/\/+$/, '');

const V1 = '/api/v1';

export const DEFAULT_TIMEOUT_MS = 15_000;
export const HEALTH_TIMEOUT_MS = 4_000;

/**
 * Talks to the Kirtikar backend.
 *
 * No Authorization header anywhere: the demo deployment runs with
 * DEMO_MODE=true, which resolves an unauthenticated request to one shared
 * demo seller (backend/app/core/security.py). That is also what lets the
 * processed images load in a plain <img src>, since an <img> cannot carry a
 * bearer token.
 */
export class ApiClient {
  constructor(readonly base: string = API_BASE) {}

  /** Absolute URL for a relative image_urls entry. */
  mediaUrl(path: string): string {
    return path.startsWith('http') ? path : `${this.base}${path}`;
  }

  async health(signal?: AbortSignal): Promise<HealthResponse> {
    return this.json<HealthResponse>('GET', '/health', {
      timeoutMs: HEALTH_TIMEOUT_MS,
      signal,
    });
  }

  async createListing(
    clientItemId: string,
    opts: { description?: string | null; photoCount?: number } = {},
    signal?: AbortSignal,
  ): Promise<Listing> {
    return this.json<Listing>('POST', `${V1}/listings`, {
      signal,
      body: {
        client_item_id: clientItemId,
        // `extra="forbid"` on the schema means an unexpected key is a 422,
        // so only send what the server declares.
        ...(opts.description ? { description: opts.description } : {}),
        ...(opts.photoCount ? { photo_count: opts.photoCount } : {}),
      },
    });
  }

  async status(id: string, signal?: AbortSignal): Promise<ListingStatusResponse> {
    return this.json<ListingStatusResponse>('GET', `${V1}/listings/${id}/status`, {
      signal,
    });
  }

  async listing(id: string, signal?: AbortSignal): Promise<Listing> {
    return this.json<Listing>('GET', `${V1}/listings/${id}`, { signal });
  }

  /** Only the whitelisted fields; anything else is a 400 server-side. */
  async patch(id: string, changes: ListingPatch, signal?: AbortSignal): Promise<Listing> {
    return this.json<Listing>('PATCH', `${V1}/listings/${id}`, {
      body: changes,
      signal,
    });
  }

  async approveSuggestion(
    listingId: string,
    suggestionId: string,
    approved: boolean,
    signal?: AbortSignal,
  ): Promise<unknown> {
    return this.json(
      'POST',
      `${V1}/listings/${listingId}/suggestions/${suggestionId}/approval`,
      { body: { approved }, signal },
    );
  }

  async consent(
    id: string,
    photo: boolean,
    story: boolean,
    signal?: AbortSignal,
  ): Promise<unknown> {
    return this.json('POST', `${V1}/listings/${id}/consent`, {
      body: { photo, story },
      signal,
    });
  }

  async publish(id: string, signal?: AbortSignal): Promise<unknown> {
    return this.json('POST', `${V1}/listings/${id}/publish`, { signal });
  }

  /**
   * Multipart upload with real byte progress.
   *
   * XMLHttpRequest rather than fetch: fetch still has no upload progress
   * event in Safari or Firefox, and the percentage in "Sending… N out of a
   * hundred" has to be real.
   */
  uploadMedia(
    listingId: string,
    file: Blob,
    filename: string,
    mediaType: 'image' | 'audio',
    onBytes?: (loaded: number) => void,
    signal?: AbortSignal,
    timeoutMs = 45_000,
  ): Promise<MediaUploadResponse> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${this.base}${V1}/listings/${listingId}/media`);
      xhr.timeout = timeoutMs;
      xhr.responseType = 'text';

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onBytes?.(e.loaded);
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText) as MediaUploadResponse);
          } catch {
            reject(new NotJsonError(xhr.getResponseHeader('content-type')));
          }
        } else {
          reject(new HttpError(xhr.status, xhr.responseText));
        }
      };
      xhr.onerror = () => reject(new NetworkError());
      xhr.ontimeout = () => reject(new TimeoutError());
      xhr.onabort = () => reject(new DOMException('Aborted', 'AbortError'));
      signal?.addEventListener('abort', () => xhr.abort(), { once: true });

      const form = new FormData();
      form.append('file', file, filename);
      form.append('media_type', mediaType);
      xhr.send(form);
    });
  }

  private async json<T>(
    method: string,
    path: string,
    opts: { body?: unknown; timeoutMs?: number; signal?: AbortSignal } = {},
  ): Promise<T> {
    const { body, timeoutMs = DEFAULT_TIMEOUT_MS, signal } = opts;

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    signal?.addEventListener('abort', () => controller.abort(), { once: true });

    let res: Response;
    try {
      res = await fetch(`${this.base}${path}`, {
        method,
        signal: controller.signal,
        headers: body ? { 'content-type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch (e) {
      if (signal?.aborted) throw e;
      throw controller.signal.aborted ? new TimeoutError() : new NetworkError();
    } finally {
      clearTimeout(timer);
    }

    const text = await res.text();
    if (!res.ok) throw new HttpError(res.status, text);

    const type = res.headers.get('content-type');
    if (!type?.includes('json')) throw new NotJsonError(type);

    return JSON.parse(text) as T;
  }
}

export const api = new ApiClient();
