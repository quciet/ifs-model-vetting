using Parquet;
using Parquet.Data;

// Preserve the coordinates written by IFs, including repeated region axes.
using var input = File.OpenRead(args[0]);
using var reader = new ParquetReader(input);
DataSet data = reader.Read();
using var output = new BinaryWriter(File.Create(args[1]));
int dimensions = data.Schema.Fields.Count - 1;
output.Write(dimensions);
output.Write(data.RowCount);
foreach (var row in data)
{
    for (int axis = 0; axis < dimensions; axis++) output.Write(row.Get<short>(axis));
    object value = row[dimensions];
    output.Write(value == null ? float.NaN : Convert.ToSingle(value));
}
