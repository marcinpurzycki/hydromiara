import { describe, expect, it } from "vitest";
import { areaRequest, placeFromAnswer } from "./area-search";
import { addressVariants } from "./geocoder";

describe("address orders asked of the geocoder", () => {
  it("keeps the typed text first and adds the order the service expects", () => {
    expect(addressVariants("Marszałkowska 1, Warszawa")).toEqual(["Marszałkowska 1, Warszawa", "Warszawa, Marszałkowska 1"]);
    expect(addressVariants("ul. Warszawska 5 Płońsk")).toContain("Płońsk, ul. Warszawska 5");
    expect(addressVariants("Płońsk Warszawska 5")).toContain("Płońsk, Warszawska 5");
    expect(addressVariants("Nowy Sącz Lwowska 10")).toContain("Nowy Sącz, Lwowska 10");
  });

  it("leaves a locality name alone and drops a postal code", () => {
    expect(addressVariants("  Kazimierz   Dolny ")).toEqual(["Kazimierz Dolny"]);
    expect(addressVariants("09-100 Płońsk, Warszawska 5")[0]).toBe("Płońsk, Warszawska 5");
  });
});

describe("units named by a TERYT identifier", () => {
  it("recognises a precinct, a commune, a county and a voivodeship", () => {
    expect(areaRequest("040704_2.0020")).toMatchObject({ request: "GetRegionById", id: "040704_2.0020" });
    expect(areaRequest("040704_2.0020.")).toMatchObject({ request: "GetRegionById", id: "040704_2.0020" });
    expect(areaRequest("040704_2")).toMatchObject({ request: "GetCommuneById", id: "040704_2" });
    expect(areaRequest("0407042")).toMatchObject({ request: "GetCommuneById", id: "040704_2" });
    expect(areaRequest("142001")).toMatchObject({ request: "GetCommuneById", id: "142001" });
    expect(areaRequest("1420")).toMatchObject({ request: "GetCountyById", id: "1420" });
    expect(areaRequest("14")).toMatchObject({ request: "GetVoivodeshipById", id: "14" });
  });

  it("leaves parcels and addresses to the other searches", () => {
    expect(areaRequest("040704_2.0020.34/2")).toBeNull();
    expect(areaRequest("Krusza Podlotowa 34/2")).toBeNull();
    expect(areaRequest("Płońsk, Warszawska 5")).toBeNull();
  });

  it("reads the extent of a found unit and refuses an empty answer", () => {
    const asked = areaRequest("040704_2.0020")!;
    const place = placeFromAnswer("0\nKrusza Podlotowa|Inowrocław|18.18,52.73,18.22,52.76\n", asked);
    expect(place).toMatchObject({
      label: "obręb Krusza Podlotowa, gmina Inowrocław",
      bounds: [
        [52.73, 18.18],
        [52.76, 18.22],
      ],
    });
    expect(placeFromAnswer("-1 brak wyników\n", asked)).toBeNull();
  });
});
