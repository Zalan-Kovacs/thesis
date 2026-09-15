function Health({ health }: { health: any }) {
    return (
        <div>
            <h1>Health</h1>
            {health ? (
            <pre>
                {JSON.stringify(health, null, 2)}
            </pre>
            ) : (
            <p>Loading...</p>
            )}
        </div>
    )
}

export default Health;