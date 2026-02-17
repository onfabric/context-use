/**
 * Payload builder helpers (ported from Python aertex builders).
 */
import {
  type ProfileType,
  type PersonType,
  type CollectionType,
  type ApplicationType,
  type ThreadPayload,
  CURRENT_THREAD_PAYLOAD_VERSION,
} from "./models.js";

// ---------------------------------------------------------------------------
// ProfileBuilder
// ---------------------------------------------------------------------------

export class ProfileBuilder {
  private url?: string;
  private _name?: string;
  private _isActor = false;

  constructor(url?: string) {
    this.url = url;
  }

  setActor(): this {
    this._isActor = true;
    return this;
  }

  withName(name: string): this {
    this._name = name;
    return this;
  }

  build(): ProfileType | PersonType {
    if (this._isActor) {
      const p: PersonType = { "@type": "Person" };
      if (this._name !== undefined) p.name = this._name;
      if (this.url !== undefined) p.url = this.url;
      return p;
    }
    const p: ProfileType = { "@type": "Profile" };
    if (this._name !== undefined) p.name = this._name;
    if (this.url !== undefined) p.url = this.url;
    return p;
  }
}

// ---------------------------------------------------------------------------
// CollectionBuilder
// ---------------------------------------------------------------------------

export class CollectionBuilder {
  private _name?: string;
  private _id?: string;

  withName(name: string): this {
    this._name = name;
    return this;
  }

  withId(id: string): this {
    this._id = id;
    return this;
  }

  build(): CollectionType {
    const c: CollectionType = { "@type": "Collection" };
    if (this._name !== undefined) c.name = this._name;
    if (this._id !== undefined) c["@id"] = this._id;
    return c;
  }
}

// ---------------------------------------------------------------------------
// PublishedBuilder
// ---------------------------------------------------------------------------

export class PublishedBuilder {
  private _published: Date;

  constructor(published: Date) {
    if (!(published instanceof Date) || isNaN(published.getTime())) {
      throw new Error("PublishedBuilder requires a valid Date");
    }
    this._published = published;
  }

  build(): Date {
    return this._published;
  }
}

// ---------------------------------------------------------------------------
// Base builder
// ---------------------------------------------------------------------------

export abstract class BaseThreadPayloadBuilder {
  getVersion(): string {
    return CURRENT_THREAD_PAYLOAD_VERSION;
  }

  abstract build(parsedItem: any): ThreadPayload;
}

