// PGL Mocap Live Link - Live Link source that receives PGL Mocap body tracking over UDP (JSON).

#pragma once

#include "CoreMinimal.h"
#include "ILiveLinkSource.h"
#include "HAL/Runnable.h"
#include "LiveLinkTypes.h"

#include <atomic>

class FRunnableThread;
class FSocket;
class ILiveLinkClient;
class ISocketSubsystem;
class FJsonObject;

class PGLMOCAPLIVELINK_API FPGLMocapLiveLinkSource : public ILiveLinkSource, public FRunnable
{
public:
	explicit FPGLMocapLiveLinkSource(int32 InPort);
	virtual ~FPGLMocapLiveLinkSource();

	// ILiveLinkSource
	virtual void ReceiveClient(ILiveLinkClient* InClient, FGuid InSourceGuid) override;
	virtual bool IsSourceStillValid() const override;
	virtual bool RequestSourceShutdown() override;
	virtual FText GetSourceType() const override;
	virtual FText GetSourceMachineName() const override;
	virtual FText GetSourceStatus() const override;

	// FRunnable
	virtual bool Init() override { return true; }
	virtual uint32 Run() override;
	virtual void Stop() override;
	virtual void Exit() override {}

private:
	void HandlePacket(const uint8* Data, int32 Size);
	void HandlePerson(const FString& Prefix, const TSharedPtr<FJsonObject>& Person);
	void HandleCurves(const FString& Base, const TSharedPtr<FJsonObject>& Person, TArray<FName>& Owned);
	void RemovePerson(const FString& Prefix, int32 PersonId);

	std::atomic<ILiveLinkClient*> Client{nullptr};
	FGuid SourceGuid;

	int32 Port = 54321;
	FSocket* Socket = nullptr;
	ISocketSubsystem* SocketSubsystem = nullptr;
	FRunnableThread* Thread = nullptr;
	std::atomic<bool> bStopping{false};

	// State, touched only by the receiver thread
	TMap<FName, TArray<FName>> SkeletonSubjects;   // skeleton subject -> bone names
	TSet<FName> TransformSubjects;                 // point subjects
	TMap<FName, TArray<FName>> CurveSubjects;      // face subject -> curve names
	TMap<int32, TArray<FName>> PersonSubjects;     // person id -> all of its subjects

	// Shown in the Live Link window
	mutable FCriticalSection StatusLock;
	FString LastSender;
	double LastPacketTime = 0.0;
	int32 LastPersons = 0;
	TArray<uint8> RecvBuffer;
};
