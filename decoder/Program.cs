using Parquet;
using Parquet.Data;
using System.Text.Json;

void ConvertPayload(string source, string target)
{
    using var input = File.OpenRead(source);
    using var reader = new ParquetReader(input);
    DataSet data = reader.Read();
    using var output = new BinaryWriter(File.Create(target));
    int dimensions = data.Schema.Fields.Count - 1;
    output.Write(dimensions);
    output.Write(data.RowCount);
    foreach (var row in data)
    {
        for (int axis = 0; axis < dimensions; axis++) output.Write(row.Get<short>(axis));
        object value = row[dimensions];
        output.Write(value == null ? float.NaN : Convert.ToSingle(value));
    }
}

if (args.Length == 1 && args[0] == "--serve")
{
    string line;
    while ((line = Console.ReadLine()) != null)
    {
        try
        {
            var paths = JsonSerializer.Deserialize<string[]>(line)!;
            if (paths.Length != 2) throw new ArgumentException("Expected input and output paths");
            ConvertPayload(paths[0], paths[1]);
            Console.WriteLine(JsonSerializer.Serialize(new { ok = true }));
        }
        catch (Exception error)
        {
            Console.WriteLine(JsonSerializer.Serialize(new { ok = false, error = error.Message }));
        }
        Console.Out.Flush();
    }
}
else
{
    ConvertPayload(args[0], args[1]);
}
