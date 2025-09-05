from backend.app.core.qdrant import get_qdrant

def main():
    q = get_qdrant()
    c = q.get_collections()
    print("Qdrant reachable. Collections:", getattr(c, 'collections', c))

if __name__ == "__main__":
    main()
