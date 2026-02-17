/**
 * Unit tests for ActivityStreams payload models.
 */
import { describe, test, expect } from "bun:test";
import {
  makeApplication,
  makeTextMessage,
  makeSendMessage,
  makeReceiveMessage,
  makeCreateObject,
  makeImage,
  makeVideo,
  makeThreadPayload,
  uniqueKeySuffix,
  toDict,
  getPreview,
  getTextMessagePreview,
  getCreateObjectPreview,
  getSendMessagePreview,
  getReceiveMessagePreview,
  type FibreSendMessage,
  type FibreReceiveMessage,
  type FibreCreateObject,
} from "../src/payload/models.js";

describe("FibreModels", () => {
  test("text message preview", () => {
    const msg = makeTextMessage("Hello World");
    expect(getTextMessagePreview(msg)).toBe('message "Hello World"');
  });

  test("text message truncation", () => {
    const long = "x".repeat(200);
    const msg = makeTextMessage(long);
    const preview = getTextMessagePreview(msg);
    expect(preview).toContain("...");
    expect(preview.length).toBeLessThan(120);
  });

  test("send message roundtrip", () => {
    const msg = makeTextMessage("hi");
    const target = makeApplication("assistant");
    const send = makeSendMessage({ object: msg, target });

    const d = toDict(send);
    expect(d.fibre_kind).toBe("SendMessage");
    expect(d.object.content).toBe("hi");
    expect(d.target.name).toBe("assistant");

    // Unique key should be deterministic
    expect(uniqueKeySuffix(d)).toBe(uniqueKeySuffix(d));
  });

  test("receive message preview", () => {
    const msg = makeTextMessage("world");
    const actor = makeApplication("bot");
    const recv = makeReceiveMessage({ object: msg, actor });

    const preview = getReceiveMessagePreview(recv, "TestProvider");
    expect(preview).toContain("Received");
    expect(preview).toContain("bot");
  });

  test("create object image", () => {
    const img = makeImage({ url: "http://example.com/pic.jpg" });
    const create = makeCreateObject({ object: img });
    expect(getCreateObjectPreview(create, "Instagram")).toBe(
      "Posted image on Instagram",
    );
  });

  test("create object video", () => {
    const vid = makeVideo({ url: "http://example.com/clip.mp4" });
    const create = makeCreateObject({ object: vid });
    expect(getCreateObjectPreview(create)).toBe("Posted video");
  });
});

describe("makeThreadPayload", () => {
  test("send message", () => {
    const data = {
      "@type": "Create",
      fibre_kind: "SendMessage",
      object: {
        "@type": "Note",
        fibre_kind: "TextMessage",
        content: "hi",
      },
      target: { "@type": "Application", name: "bot" },
    };
    const payload = makeThreadPayload(data);
    expect(payload.fibre_kind).toBe("SendMessage");
  });

  test("create object", () => {
    const data = {
      "@type": "Create",
      fibre_kind: "Create",
      object: { "@type": "Video", url: "http://example.com/v.mp4" },
    };
    const payload = makeThreadPayload(data);
    expect(payload.fibre_kind).toBe("Create");
  });
});

describe("FibreAsat", () => {
  test("getPreview dispatches correctly", () => {
    const msg = makeTextMessage("test");
    const app = makeApplication("assistant");
    const send = makeSendMessage({
      object: msg,
      target: app,
      published: new Date(2024, 0, 1).toISOString(),
    });
    const preview = getPreview(send, "ChatGPT");
    expect(preview).toContain("Sent");
    expect(preview).toContain("ChatGPT");
  });
});

