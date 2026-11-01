#include "PGLMocapLiveLinkSourceFactory.h"

#include "PGLMocapLiveLinkSource.h"
#include "SPGLMocapLiveLinkSourcePanel.h"

#define LOCTEXT_NAMESPACE "PGLMocapLiveLinkSourceFactory"

FText UPGLMocapLiveLinkSourceFactory::GetSourceDisplayName() const
{
	return LOCTEXT("SourceDisplayName", "PGL Mocap");
}

FText UPGLMocapLiveLinkSourceFactory::GetSourceTooltip() const
{
	return LOCTEXT("SourceTooltip", "Receives body tracking from PGL Mocap over UDP");
}

TSharedPtr<SWidget> UPGLMocapLiveLinkSourceFactory::BuildCreationPanel(FOnLiveLinkSourceCreated InOnLiveLinkSourceCreated) const
{
	return SNew(SPGLMocapLiveLinkSourcePanel)
		.OnAddClicked(SPGLMocapLiveLinkSourcePanel::FOnAddClicked::CreateUObject(
			this, &UPGLMocapLiveLinkSourceFactory::OnAddClicked, InOnLiveLinkSourceCreated));
}

TSharedPtr<ILiveLinkSource> UPGLMocapLiveLinkSourceFactory::CreateSource(const FString& ConnectionString) const
{
	// ConnectionString is the UDP port (saved in Live Link presets)
	int32 Port = 54321;
	if (!ConnectionString.IsEmpty())
	{
		LexFromString(Port, *ConnectionString);
	}
	if (Port <= 0 || Port > 65535)
	{
		Port = 54321;
	}
	return MakeShared<FPGLMocapLiveLinkSource>(Port);
}

void UPGLMocapLiveLinkSourceFactory::OnAddClicked(int32 Port, FOnLiveLinkSourceCreated InOnLiveLinkSourceCreated) const
{
	InOnLiveLinkSourceCreated.ExecuteIfBound(MakeShared<FPGLMocapLiveLinkSource>(Port), FString::FromInt(Port));
}

#undef LOCTEXT_NAMESPACE
