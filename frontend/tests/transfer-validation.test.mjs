import assert from "node:assert/strict";
import { test } from "node:test";
import { build } from "esbuild";

const { outputFiles } = await build({
  entryPoints: [new URL("../src/api/transfer-validation.ts", import.meta.url).pathname],
  bundle: true, write: false, format: "esm", platform: "node",
});
const { validarEnvio } = await import(`data:text/javascript;base64,${Buffer.from(outputFiles[0].text).toString("base64")}`);

test("convierte decimales sin perder céntimos y normaliza el alias", () => {
  for (const importe of ["30.10", "30,10"]) {
    const resultado = validarEnvio(" LUIS ", importe, "ana", 5000);
    assert.equal(resultado.centimos, 3010);
    assert.equal(resultado.alias, "luis");
    assert.equal(resultado.motivo, null);
  }
});

test("impide superar el saldo, pero permite enviar el saldo exacto", () => {
  assert.equal(validarEnvio("luis", "50.01", "ana", 5000).sinSaldo, true);
  assert.ok(validarEnvio("luis", "50.01", "ana", 5000).motivo);
  assert.equal(validarEnvio("luis", "50", "ana", 5000).motivo, null);
});

test("impide el envío propio incluso con mayúsculas y espacios", () => {
  assert.ok(validarEnvio(" ANA ", "10", "Ana", 5000).errorDestino);
});

test("exige datos válidos y saldo cargado antes de revisar", () => {
  for (const [alias, importe, saldo] of [
    ["", "10", 5000], ["ab", "10", 5000], ["a b", "10", 5000],
    ["a".repeat(33), "10", 5000], ["luis", "", 5000],
    ["luis", "0", 5000], ["luis", "-1", 5000], ["luis", "1.001", 5000],
    ["luis", "10", null],
  ]) assert.ok(validarEnvio(alias, importe, "ana", saldo).motivo, `${alias}/${importe}/${saldo}`);
});
