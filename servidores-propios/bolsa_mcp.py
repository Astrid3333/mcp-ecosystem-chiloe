from fastmcp import FastMCP
import yfinance as yf

mcp = FastMCP("Bolsa MCP")

@mcp.tool()
def obtener_precio(ticker: str) -> dict:
    """Obtiene el precio actual y datos básicos de un ticker (ej: AAPL, BTC-USD)."""
    accion = yf.Ticker(ticker)
    info = accion.history(period="1d")
    if info.empty:
        return {"error": f"No se encontraron datos para {ticker}"}
    ultimo = info.iloc[-1]
    return {
        "ticker": ticker,
        "precio_cierre": round(float(ultimo["Close"]), 2),
        "volumen": int(ultimo["Volume"]),
        "fecha": str(info.index[-1].date())
    }

if __name__ == "__main__":
    mcp.run()
