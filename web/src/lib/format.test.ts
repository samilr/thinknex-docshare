import { describe, expect, it } from "vitest";
import { toCsv } from "./format";

describe("toCsv", () => {
  it("agrega BOM, usa ; y escapa comillas, saltos y objetos", () => {
    const csv = toCsv([
      { id: 1, texto: 'dice "hola"; chao', meta: { a: 1 } },
      { id: 2, texto: null, meta: null },
    ]);
    expect(csv.charCodeAt(0)).toBe(0xfeff);
    const [header, first, second] = csv.slice(1).split("\r\n");
    expect(header).toBe("id;texto;meta");
    expect(first).toBe('1;"dice ""hola""; chao";"{""a"":1}"');
    expect(second).toBe("2;;");
  });
});
